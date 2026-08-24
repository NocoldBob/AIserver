"""Application and task runtime."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any, get_type_hints
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, create_model

from . import models
from .context import TaskContext
from .middleware import BearerTokenMiddleware, RequestSizeLimitMiddleware
from .storage import SQLiteJobStore

TaskFunction = Callable[..., Any]
Hook = Callable[[], Any]
_TASK_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(slots=True)
class _TaskSpec:
    name: str
    function: TaskFunction
    input_model: type[BaseModel]
    context_parameter: str | None
    timeout_seconds: float | None
    concurrency: int
    description: str | None
    semaphore: asyncio.Semaphore | None = None


@dataclass(slots=True)
class _FileTaskSpec:
    name: str
    function: TaskFunction
    file_parameter: str
    file_parameter_is_input_file: bool
    filename_parameter: str | None
    content_type_parameter: str | None
    context_parameter: str | None
    timeout_seconds: float | None
    concurrency: int
    max_file_bytes: int | None
    description: str | None
    semaphore: asyncio.Semaphore | None = None


@dataclass(slots=True)
class _JobRuntime:
    snapshot: models.JobSnapshot
    lock: threading.Lock = field(default_factory=threading.Lock)
    runner: asyncio.Task[None] | None = None


class AIServer:
    """A small, single-process server for Python inference functions."""

    def __init__(
        self,
        name: str = "AIserver",
        *,
        version: str = "0.1.2",
        token: str | None = None,
        max_request_bytes: int = 16 * 1024 * 1024,
        max_job_history: int = 1_000,
        job_store: SQLiteJobStore | str | Path | None = None,
        expose_errors: bool = False,
    ) -> None:
        if max_job_history < 1:
            raise ValueError("max_job_history must be at least one")

        self.name = name
        self.version = version
        self.token = token if token is not None else os.getenv("AISERVER_TOKEN")
        self.max_request_bytes = max_request_bytes
        self.max_job_history = max_job_history
        self.job_store = self._coerce_job_store(job_store)
        self.expose_errors = expose_errors
        self._tasks: dict[str, _TaskSpec | _FileTaskSpec] = {}
        self._jobs: dict[str, _JobRuntime] = {}
        self._startup_hooks: list[Hook] = []
        self._shutdown_hooks: list[Hook] = []

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            await self._run_hooks(self._startup_hooks)
            try:
                yield
            finally:
                runners = [job.runner for job in self._jobs.values() if job.runner is not None]
                for runner in runners:
                    if not runner.done():
                        runner.cancel()
                if runners:
                    await asyncio.gather(*runners, return_exceptions=True)
                await self._run_hooks(reversed(self._shutdown_hooks))

        self.app = FastAPI(title=name, version=version, lifespan=lifespan)
        self.app.add_middleware(RequestSizeLimitMiddleware, max_request_bytes=max_request_bytes)
        self.app.add_middleware(BearerTokenMiddleware, token=self.token)
        self._load_persisted_jobs()
        self._register_system_routes()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)

    def task(
        self,
        name: str | None = None,
        *,
        concurrency: int = 1,
        timeout: float | None = 300,
        description: str | None = None,
    ) -> Callable[[TaskFunction], TaskFunction]:
        """Register a function as a direct and asynchronous inference task."""

        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be greater than zero or None")

        def decorator(function: TaskFunction) -> TaskFunction:
            task_name = name or function.__name__.replace("_", "-")
            if not _TASK_NAME.fullmatch(task_name):
                raise ValueError(
                    "task name must start with a lowercase letter and contain only "
                    "lowercase letters, numbers, '-' or '_'"
                )
            if task_name in self._tasks:
                raise ValueError(f"task {task_name!r} is already registered")

            input_model, context_parameter = self._build_input_model(task_name, function)
            spec = _TaskSpec(
                name=task_name,
                function=function,
                input_model=input_model,
                context_parameter=context_parameter,
                timeout_seconds=timeout,
                concurrency=concurrency,
                description=description or inspect.getdoc(function),
            )
            self._tasks[task_name] = spec
            self._register_task_routes(spec)
            return function

        return decorator

    def file_task(
        self,
        name: str | None = None,
        *,
        concurrency: int = 1,
        timeout: float | None = 300,
        max_file_bytes: int | None = None,
        description: str | None = None,
    ) -> Callable[[TaskFunction], TaskFunction]:
        """Register a multipart file inference task.

        The decorated function must declare exactly one ``bytes`` or ``InputFile``
        parameter. Optional ``filename: str``, ``content_type: str`` and
        ``TaskContext`` parameters are populated automatically for ``bytes`` tasks.
        """

        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be greater than zero or None")
        if max_file_bytes is not None and max_file_bytes < 1:
            raise ValueError("max_file_bytes must be at least one or None")

        def decorator(function: TaskFunction) -> TaskFunction:
            task_name = name or function.__name__.replace("_", "-")
            if not _TASK_NAME.fullmatch(task_name):
                raise ValueError(
                    "task name must start with a lowercase letter and contain only "
                    "lowercase letters, numbers, '-' or '_'"
                )
            if task_name in self._tasks:
                raise ValueError(f"task {task_name!r} is already registered")

            spec = self._build_file_task_spec(
                task_name,
                function,
                concurrency=concurrency,
                timeout=timeout,
                max_file_bytes=max_file_bytes,
                description=description or inspect.getdoc(function),
            )
            self._tasks[task_name] = spec
            self._register_file_task_routes(spec)
            return function

        return decorator

    def on_startup(self, function: Hook) -> Hook:
        self._startup_hooks.append(function)
        return function

    def on_shutdown(self, function: Hook) -> Hook:
        self._shutdown_hooks.append(function)
        return function

    def _register_system_routes(self) -> None:
        @self.app.get("/health", response_model=models.ServiceHealth, tags=["service"])
        async def health() -> models.ServiceHealth:
            return models.ServiceHealth(status="ok", name=self.name, version=self.version)

        @self.app.get("/ready", response_model=models.ServiceHealth, tags=["service"])
        async def ready() -> models.ServiceHealth:
            return models.ServiceHealth(status="ready", name=self.name, version=self.version)

        @self.app.get("/v1/tasks", response_model=list[models.TaskDescriptor], tags=["tasks"])
        async def list_tasks() -> list[models.TaskDescriptor]:
            return [
                models.TaskDescriptor(
                    name=spec.name,
                    description=spec.description,
                    timeout_seconds=spec.timeout_seconds,
                    concurrency=spec.concurrency,
                    input_schema=self._task_input_schema(spec),
                )
                for spec in self._tasks.values()
            ]

        @self.app.get("/v1/jobs", response_model=list[models.JobSnapshot], tags=["jobs"])
        async def list_jobs() -> list[models.JobSnapshot]:
            snapshots = [job.snapshot.model_copy(deep=True) for job in self._jobs.values()]
            return sorted(snapshots, key=lambda job: job.created_at, reverse=True)

        @self.app.get("/v1/jobs/{job_id}", response_model=models.JobSnapshot, tags=["jobs"])
        async def get_job(job_id: str) -> models.JobSnapshot:
            runtime = self._jobs.get(job_id)
            if runtime is None:
                raise HTTPException(status_code=404, detail="Job not found")
            with runtime.lock:
                return runtime.snapshot.model_copy(deep=True)

        @self.app.delete("/v1/jobs/{job_id}", status_code=204, tags=["jobs"])
        async def delete_job(job_id: str) -> Response:
            runtime = self._jobs.pop(job_id, None)
            if runtime is None:
                raise HTTPException(status_code=404, detail="Job not found")
            if runtime.runner is not None and not runtime.runner.done():
                runtime.runner.cancel()
            if self.job_store is not None:
                self.job_store.delete(job_id)
            return Response(status_code=204)

        @self.app.get("/v1/jobs/{job_id}/result-file", tags=["jobs"])
        async def get_job_result_file(job_id: str) -> Response:
            runtime = self._jobs.get(job_id)
            if runtime is None:
                raise HTTPException(status_code=404, detail="Job not found")
            with runtime.lock:
                snapshot = runtime.snapshot.model_copy(deep=True)
            result = self._extract_file_result(snapshot.result)
            if result is None:
                raise HTTPException(status_code=404, detail="Job result is not a file")
            headers = {}
            if result.filename:
                headers["Content-Disposition"] = f'attachment; filename="{result.filename}"'
            return Response(
                content=result.data,
                media_type=result.content_type,
                headers=headers,
            )

    def _register_task_routes(self, spec: _TaskSpec) -> None:
        async def run_direct(payload: BaseModel) -> models.TaskExecutionResponse:
            started = perf_counter()
            try:
                result = await self._execute(spec, payload, TaskContext(lambda _p, _m: None))
            except TimeoutError as error:
                raise HTTPException(status_code=504, detail="Task timed out") from error
            except HTTPException:
                raise
            except Exception as error:
                detail = str(error) if self.expose_errors else "Task execution failed"
                raise HTTPException(status_code=500, detail=detail) from error
            return models.TaskExecutionResponse(
                task=spec.name,
                elapsed_seconds=perf_counter() - started,
                result=self._encode_result(result),
            )

        run_direct.__name__ = f"run_{spec.name.replace('-', '_')}"
        run_direct.__annotations__["payload"] = spec.input_model
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/run",
            run_direct,
            methods=["POST"],
            response_model=models.TaskExecutionResponse,
            tags=["tasks"],
            summary=f"Run {spec.name}",
        )

        async def submit_job(payload: BaseModel) -> models.JobAccepted:
            self._prune_jobs()
            job_id = uuid4().hex
            runtime = _JobRuntime(
                snapshot=models.JobSnapshot(
                    id=job_id,
                    task=spec.name,
                    state=models.JobState.QUEUED,
                    created_at=datetime.now(UTC),
                )
            )
            self._jobs[job_id] = runtime
            self._persist_job(runtime)
            runtime.runner = asyncio.create_task(self._run_job(runtime, spec, payload))
            return models.JobAccepted(
                id=job_id,
                task=spec.name,
                state=models.JobState.QUEUED,
                status_url=f"/v1/jobs/{job_id}",
            )

        submit_job.__name__ = f"submit_{spec.name.replace('-', '_')}"
        submit_job.__annotations__["payload"] = spec.input_model
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/jobs",
            submit_job,
            methods=["POST"],
            status_code=202,
            response_model=models.JobAccepted,
            tags=["jobs"],
            summary=f"Submit {spec.name}",
        )

    def _register_file_task_routes(self, spec: _FileTaskSpec) -> None:
        async def run_direct(file: UploadFile) -> models.TaskExecutionResponse:
            started = perf_counter()
            try:
                kwargs = await self._file_kwargs(spec, file)
                result = await self._execute_kwargs(spec, kwargs, TaskContext(lambda _p, _m: None))
            except TimeoutError as error:
                raise HTTPException(status_code=504, detail="Task timed out") from error
            except HTTPException:
                raise
            except Exception as error:
                detail = str(error) if self.expose_errors else "Task execution failed"
                raise HTTPException(status_code=500, detail=detail) from error
            return models.TaskExecutionResponse(
                task=spec.name,
                elapsed_seconds=perf_counter() - started,
                result=self._encode_result(result),
            )

        run_direct.__name__ = f"run_{spec.name.replace('-', '_')}"
        run_direct.__signature__ = self._file_endpoint_signature()
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/run",
            run_direct,
            methods=["POST"],
            response_model=models.TaskExecutionResponse,
            tags=["tasks"],
            summary=f"Run {spec.name}",
        )

        async def run_direct_base64(
            payload: models.Base64FileInput,
        ) -> models.TaskExecutionResponse:
            started = perf_counter()
            try:
                kwargs = self._base64_file_kwargs(spec, payload)
                result = await self._execute_kwargs(spec, kwargs, TaskContext(lambda _p, _m: None))
            except TimeoutError as error:
                raise HTTPException(status_code=504, detail="Task timed out") from error
            except HTTPException:
                raise
            except Exception as error:
                detail = str(error) if self.expose_errors else "Task execution failed"
                raise HTTPException(status_code=500, detail=detail) from error
            return models.TaskExecutionResponse(
                task=spec.name,
                elapsed_seconds=perf_counter() - started,
                result=self._encode_result(result),
            )

        run_direct_base64.__name__ = f"run_{spec.name.replace('-', '_')}_base64"
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/run-base64",
            run_direct_base64,
            methods=["POST"],
            response_model=models.TaskExecutionResponse,
            tags=["tasks"],
            summary=f"Run {spec.name} from base64 JSON",
        )

        async def submit_job(file: UploadFile) -> models.JobAccepted:
            self._prune_jobs()
            kwargs = await self._file_kwargs(spec, file)
            job_id = uuid4().hex
            runtime = _JobRuntime(
                snapshot=models.JobSnapshot(
                    id=job_id,
                    task=spec.name,
                    state=models.JobState.QUEUED,
                    created_at=datetime.now(UTC),
                )
            )
            self._jobs[job_id] = runtime
            self._persist_job(runtime)
            runtime.runner = asyncio.create_task(self._run_job(runtime, spec, kwargs))
            return models.JobAccepted(
                id=job_id,
                task=spec.name,
                state=models.JobState.QUEUED,
                status_url=f"/v1/jobs/{job_id}",
            )

        submit_job.__name__ = f"submit_{spec.name.replace('-', '_')}"
        submit_job.__signature__ = self._file_endpoint_signature()
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/jobs",
            submit_job,
            methods=["POST"],
            status_code=202,
            response_model=models.JobAccepted,
            tags=["jobs"],
            summary=f"Submit {spec.name}",
        )

        async def submit_job_base64(payload: models.Base64FileInput) -> models.JobAccepted:
            self._prune_jobs()
            kwargs = self._base64_file_kwargs(spec, payload)
            job_id = uuid4().hex
            runtime = _JobRuntime(
                snapshot=models.JobSnapshot(
                    id=job_id,
                    task=spec.name,
                    state=models.JobState.QUEUED,
                    created_at=datetime.now(UTC),
                )
            )
            self._jobs[job_id] = runtime
            self._persist_job(runtime)
            runtime.runner = asyncio.create_task(self._run_job(runtime, spec, kwargs))
            return models.JobAccepted(
                id=job_id,
                task=spec.name,
                state=models.JobState.QUEUED,
                status_url=f"/v1/jobs/{job_id}",
            )

        submit_job_base64.__name__ = f"submit_{spec.name.replace('-', '_')}_base64"
        self.app.add_api_route(
            f"/v1/tasks/{spec.name}/jobs-base64",
            submit_job_base64,
            methods=["POST"],
            status_code=202,
            response_model=models.JobAccepted,
            tags=["jobs"],
            summary=f"Submit {spec.name} from base64 JSON",
        )

    async def _run_job(
        self,
        runtime: _JobRuntime,
        spec: _TaskSpec | _FileTaskSpec,
        payload: BaseModel | dict[str, Any],
    ) -> None:
        with runtime.lock:
            runtime.snapshot.state = models.JobState.RUNNING
            runtime.snapshot.started_at = datetime.now(UTC)
            self._persist_job(runtime)

        def report(progress: float | None, message: str | None) -> None:
            with runtime.lock:
                if runtime.snapshot.state is not models.JobState.RUNNING:
                    return
                if progress is not None:
                    runtime.snapshot.progress = progress
                if message is not None:
                    runtime.snapshot.message = message

        try:
            if isinstance(payload, BaseModel):
                result = await self._execute(spec, payload, TaskContext(report))
            else:
                result = await self._execute_kwargs(spec, payload, TaskContext(report))
            with runtime.lock:
                runtime.snapshot.state = models.JobState.SUCCEEDED
                runtime.snapshot.progress = 1.0
                runtime.snapshot.result = self._encode_result(result)
        except TimeoutError:
            with runtime.lock:
                runtime.snapshot.state = models.JobState.TIMED_OUT
                runtime.snapshot.error = models.JobError(code="timeout", message="Task timed out")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            message = str(error) if self.expose_errors else "Task execution failed"
            with runtime.lock:
                runtime.snapshot.state = models.JobState.FAILED
                runtime.snapshot.error = models.JobError(code="task_failed", message=message)
        finally:
            with runtime.lock:
                runtime.snapshot.finished_at = datetime.now(UTC)
                self._persist_job(runtime)

    async def _execute(
        self,
        spec: _TaskSpec,
        payload: BaseModel,
        context: TaskContext,
    ) -> Any:
        kwargs = payload.model_dump()
        return await self._execute_kwargs(spec, kwargs, context)

    async def _execute_kwargs(
        self,
        spec: _TaskSpec | _FileTaskSpec,
        kwargs: dict[str, Any],
        context: TaskContext,
    ) -> Any:
        if spec.semaphore is None:
            spec.semaphore = asyncio.Semaphore(spec.concurrency)

        if spec.context_parameter is not None:
            kwargs[spec.context_parameter] = context

        async def invoke() -> Any:
            async with spec.semaphore:
                if inspect.iscoroutinefunction(spec.function):
                    return await spec.function(**kwargs)
                return await asyncio.to_thread(partial(spec.function, **kwargs))

        if spec.timeout_seconds is None:
            return await invoke()
        return await asyncio.wait_for(invoke(), timeout=spec.timeout_seconds)

    async def _file_kwargs(self, spec: _FileTaskSpec, file: UploadFile) -> dict[str, Any]:
        content = await file.read()
        self._validate_file_size(spec, len(content))
        input_file = models.InputFile(
            data=content,
            filename=file.filename,
            content_type=file.content_type,
        )
        return self._input_file_kwargs(spec, input_file)

    def _base64_file_kwargs(
        self,
        spec: _FileTaskSpec,
        payload: models.Base64FileInput,
    ) -> dict[str, Any]:
        input_file = payload.to_input_file()
        self._validate_file_size(spec, len(input_file.data))
        return self._input_file_kwargs(spec, input_file)

    def _input_file_kwargs(
        self,
        spec: _FileTaskSpec,
        input_file: models.InputFile,
    ) -> dict[str, Any]:
        if spec.file_parameter_is_input_file:
            kwargs: dict[str, Any] = {spec.file_parameter: input_file}
        else:
            kwargs = {spec.file_parameter: input_file.data}
        if spec.filename_parameter is not None:
            kwargs[spec.filename_parameter] = input_file.filename
        if spec.content_type_parameter is not None:
            kwargs[spec.content_type_parameter] = input_file.content_type
        return kwargs

    @staticmethod
    def _validate_file_size(spec: _FileTaskSpec, size: int) -> None:
        if spec.max_file_bytes is not None and size > spec.max_file_bytes:
            raise HTTPException(status_code=413, detail="Uploaded file is too large")

    def _build_input_model(
        self,
        task_name: str,
        function: TaskFunction,
    ) -> tuple[type[BaseModel], str | None]:
        signature = inspect.signature(function)
        try:
            hints = get_type_hints(function, include_extras=True)
        except (NameError, TypeError):
            hints = {}

        fields: dict[str, tuple[Any, Any]] = {}
        context_parameter: str | None = None
        for parameter in signature.parameters.values():
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise ValueError(
                    f"task {task_name!r} uses unsupported parameter {parameter.name!r}"
                )

            annotation = hints.get(parameter.name, parameter.annotation)
            if annotation is TaskContext:
                if context_parameter is not None:
                    raise ValueError("a task can declare only one TaskContext parameter")
                context_parameter = parameter.name
                continue
            if annotation is inspect.Parameter.empty:
                annotation = Any
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            fields[parameter.name] = (annotation, default)

        model_name = "".join(part.capitalize() for part in re.split(r"[-_]", task_name)) + "Input"
        input_model = create_model(model_name, __base__=models.StrictInputModel, **fields)
        return input_model, context_parameter

    def _build_file_task_spec(
        self,
        task_name: str,
        function: TaskFunction,
        *,
        concurrency: int,
        timeout: float | None,
        max_file_bytes: int | None,
        description: str | None,
    ) -> _FileTaskSpec:
        signature = inspect.signature(function)
        try:
            hints = get_type_hints(function, include_extras=True)
        except (NameError, TypeError):
            hints = {}

        file_parameter: str | None = None
        file_parameter_is_input_file = False
        filename_parameter: str | None = None
        content_type_parameter: str | None = None
        context_parameter: str | None = None
        for parameter in signature.parameters.values():
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise ValueError(
                    f"file task {task_name!r} uses unsupported parameter {parameter.name!r}"
                )

            annotation = hints.get(parameter.name, parameter.annotation)
            if annotation is TaskContext:
                if context_parameter is not None:
                    raise ValueError("a file task can declare only one TaskContext parameter")
                context_parameter = parameter.name
            elif annotation is bytes:
                if file_parameter is not None:
                    raise ValueError("a file task can declare only one bytes file parameter")
                file_parameter = parameter.name
            elif annotation is models.InputFile:
                if file_parameter is not None:
                    raise ValueError("a file task can declare only one file parameter")
                file_parameter = parameter.name
                file_parameter_is_input_file = True
            elif annotation is str and parameter.name == "filename":
                filename_parameter = parameter.name
            elif annotation in {str, str | None} and parameter.name == "content_type":
                content_type_parameter = parameter.name
            else:
                raise ValueError(
                    "file tasks support one bytes or InputFile parameter plus optional "
                    "filename: str, content_type: str | None and TaskContext for bytes tasks"
                )

        if file_parameter is None:
            raise ValueError("file tasks must declare one bytes or InputFile parameter")
        return _FileTaskSpec(
            name=task_name,
            function=function,
            file_parameter=file_parameter,
            file_parameter_is_input_file=file_parameter_is_input_file,
            filename_parameter=filename_parameter,
            content_type_parameter=content_type_parameter,
            context_parameter=context_parameter,
            timeout_seconds=timeout,
            concurrency=concurrency,
            max_file_bytes=max_file_bytes,
            description=description,
        )

    @staticmethod
    def _file_endpoint_signature() -> inspect.Signature:
        return inspect.Signature(
            parameters=[
                inspect.Parameter(
                    "file",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=File(...),
                    annotation=UploadFile,
                )
            ],
            return_annotation=models.TaskExecutionResponse,
        )

    @staticmethod
    def _task_input_schema(spec: _TaskSpec | _FileTaskSpec) -> dict[str, Any]:
        if isinstance(spec, _TaskSpec):
            return spec.input_model.model_json_schema()
        return {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "format": "binary",
                    "description": "Multipart file upload.",
                },
                "data_base64": {
                    "type": "string",
                    "description": "Base64 file content for run-base64 and jobs-base64.",
                },
                "filename": {"type": "string"},
                "content_type": {"type": "string"},
            },
            "required": ["file"],
        }

    @staticmethod
    def _encode_result(result: Any) -> Any:
        if isinstance(result, models.FileResult):
            return result.model_dump(mode="json")
        if isinstance(result, models.InputFile):
            return models.FileResult.from_bytes(
                result.data,
                filename=result.filename,
                content_type=result.content_type or "application/octet-stream",
            ).model_dump(mode="json")
        if isinstance(result, bytes):
            return models.FileResult.from_bytes(result).model_dump(mode="json")
        if isinstance(result, dict):
            return {key: AIServer._encode_result(value) for key, value in result.items()}
        if isinstance(result, list):
            return [AIServer._encode_result(value) for value in result]
        return jsonable_encoder(result)

    @staticmethod
    def _extract_file_result(result: Any) -> models.InputFile | None:
        if not isinstance(result, dict):
            return None
        if result.get("encoding") != "base64" or not isinstance(result.get("data_base64"), str):
            return None
        try:
            return models.Base64FileInput(
                data_base64=result["data_base64"],
                filename=result.get("filename"),
                content_type=result.get("content_type") or "application/octet-stream",
            ).to_input_file()
        except ValueError:
            return None

    def _persist_job(self, runtime: _JobRuntime) -> None:
        if self.job_store is None:
            return
        self.job_store.save(runtime.snapshot.model_copy(deep=True))

    def _load_persisted_jobs(self) -> None:
        if self.job_store is None:
            return
        for snapshot in reversed(self.job_store.load(self.max_job_history)):
            if snapshot.state in {models.JobState.QUEUED, models.JobState.RUNNING}:
                snapshot.state = models.JobState.FAILED
                snapshot.finished_at = datetime.now(UTC)
                snapshot.error = models.JobError(
                    code="interrupted",
                    message="Job was interrupted before this server process started.",
                )
            runtime = _JobRuntime(snapshot=snapshot)
            self._jobs[snapshot.id] = runtime
            self._persist_job(runtime)

    @staticmethod
    def _coerce_job_store(job_store: SQLiteJobStore | str | Path | None) -> SQLiteJobStore | None:
        if job_store is None or isinstance(job_store, SQLiteJobStore):
            return job_store
        return SQLiteJobStore(job_store)

    def _prune_jobs(self) -> None:
        if len(self._jobs) < self.max_job_history:
            return
        completed = [
            (job.snapshot.finished_at or job.snapshot.created_at, job_id)
            for job_id, job in self._jobs.items()
            if job.snapshot.finished_at is not None
        ]
        if not completed:
            raise HTTPException(status_code=503, detail="Job history is full")
        _, oldest = min(completed)
        del self._jobs[oldest]
        if self.job_store is not None:
            self.job_store.delete(oldest)

    @staticmethod
    async def _run_hooks(hooks: Any) -> None:
        for hook in hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
