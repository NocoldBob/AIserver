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
from time import perf_counter
from typing import Any, get_type_hints
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, create_model

from . import models
from .context import TaskContext
from .middleware import BearerTokenMiddleware, RequestSizeLimitMiddleware

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
        version: str = "0.1.0",
        token: str | None = None,
        max_request_bytes: int = 16 * 1024 * 1024,
        max_job_history: int = 1_000,
        expose_errors: bool = False,
    ) -> None:
        if max_job_history < 1:
            raise ValueError("max_job_history must be at least one")

        self.name = name
        self.version = version
        self.token = token if token is not None else os.getenv("AISERVER_TOKEN")
        self.max_request_bytes = max_request_bytes
        self.max_job_history = max_job_history
        self.expose_errors = expose_errors
        self._tasks: dict[str, _TaskSpec] = {}
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
                    input_schema=spec.input_model.model_json_schema(),
                )
                for spec in self._tasks.values()
            ]

        @self.app.get("/v1/jobs/{job_id}", response_model=models.JobSnapshot, tags=["jobs"])
        async def get_job(job_id: str) -> models.JobSnapshot:
            runtime = self._jobs.get(job_id)
            if runtime is None:
                raise HTTPException(status_code=404, detail="Job not found")
            with runtime.lock:
                return runtime.snapshot.model_copy(deep=True)

    def _register_task_routes(self, spec: _TaskSpec) -> None:
        async def run_direct(payload: BaseModel) -> models.TaskExecutionResponse:
            started = perf_counter()
            try:
                result = await self._execute(spec, payload, TaskContext(lambda _p, _m: None))
            except TimeoutError as error:
                raise HTTPException(status_code=504, detail="Task timed out") from error
            except Exception as error:
                detail = str(error) if self.expose_errors else "Task execution failed"
                raise HTTPException(status_code=500, detail=detail) from error
            return models.TaskExecutionResponse(
                task=spec.name,
                elapsed_seconds=perf_counter() - started,
                result=jsonable_encoder(result),
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

    async def _run_job(self, runtime: _JobRuntime, spec: _TaskSpec, payload: BaseModel) -> None:
        with runtime.lock:
            runtime.snapshot.state = models.JobState.RUNNING
            runtime.snapshot.started_at = datetime.now(UTC)

        def report(progress: float | None, message: str | None) -> None:
            with runtime.lock:
                if runtime.snapshot.state is not models.JobState.RUNNING:
                    return
                if progress is not None:
                    runtime.snapshot.progress = progress
                if message is not None:
                    runtime.snapshot.message = message

        try:
            result = await self._execute(spec, payload, TaskContext(report))
            encoded = jsonable_encoder(result)
            with runtime.lock:
                runtime.snapshot.state = models.JobState.SUCCEEDED
                runtime.snapshot.progress = 1.0
                runtime.snapshot.result = encoded
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

    async def _execute(
        self,
        spec: _TaskSpec,
        payload: BaseModel,
        context: TaskContext,
    ) -> Any:
        if spec.semaphore is None:
            spec.semaphore = asyncio.Semaphore(spec.concurrency)

        kwargs = payload.model_dump()
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

    @staticmethod
    async def _run_hooks(hooks: Any) -> None:
        for hook in hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
