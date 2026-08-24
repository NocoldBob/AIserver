# AIserver

[![PyPI](https://img.shields.io/pypi/v/AIserver.svg)](https://pypi.org/project/AIserver/)
[![Python](https://img.shields.io/pypi/pyversions/AIserver.svg)](https://pypi.org/project/AIserver/)
[![CI](https://github.com/NocoldBob/AIserver/actions/workflows/ci.yml/badge.svg)](https://github.com/NocoldBob/AIserver/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-2f6f50.svg)](LICENSE)

[中文说明](docs/README.zh-CN.md)

AIserver is a lightweight, local-first Python server for exposing AI inference functions as
secure, typed, and concurrency-controlled HTTP APIs.

It is intentionally smaller than a model runtime or distributed serving platform. Bring any
Python model or pipeline you already use; AIserver handles request validation, task execution,
job status, progress, lifecycle hooks, and conservative network defaults.

## Features

- Turn typed Python functions into documented HTTP endpoints.
- Accept multipart file uploads for image, audio, and document inference tasks.
- Accept base64 JSON file inputs when multipart is inconvenient.
- Return generated files as base64-encoded `FileResult` payloads.
- Run tasks directly or submit in-memory asynchronous jobs.
- List, delete, and inspect asynchronous jobs through HTTP.
- Download `FileResult` job outputs as files.
- Optionally persist job status and results in SQLite.
- Limit concurrency per task to protect CPU, GPU, and model memory.
- Report progress from synchronous or asynchronous inference code.
- Apply per-task timeouts and bounded job history.
- Load and release models with startup and shutdown hooks.
- Protect private endpoints with `AISERVER_TOKEN`.
- Reject oversized request bodies and bind to localhost by default.
- Generate OpenAPI documentation automatically at `/docs`.
- No telemetry, model downloads, protocol proxy, or request-body logging.

## Requirements

- Python 3.11 or newer
- Windows, Linux, or macOS

## Install

```bash
pip install AIserver
```

## Quick start

Create `app.py`:

```python
from aiserver import AIServer, TaskContext

server = AIServer("demo")


@server.task(concurrency=2, timeout=30)
def classify(text: str, context: TaskContext) -> dict[str, str]:
    context.report(0.5, "running inference")
    return {"label": text.upper()}
```

Run it:

```bash
aiserver run app:server
```

Open `http://127.0.0.1:8000/docs`, or call it directly:

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks/classify/run \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

Submit the same task as a job:

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks/classify/jobs \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

Poll the returned `status_url` to read progress and the final result.

## File uploads and file results

Use `file_task` when the model expects an uploaded image, audio clip, or document:

```python
from aiserver import AIServer, FileResult, InputFile, TaskContext

server = AIServer("vision")


@server.file_task(concurrency=1, timeout=60, max_file_bytes=8 * 1024 * 1024)
def detect(
    image: InputFile,
    context: TaskContext,
) -> FileResult:
    context.report(0.5, "running detector")
    return FileResult.from_bytes(
        b"generated report",
        filename="report.txt",
        content_type="text/plain",
    )
```

Call it with multipart form data:

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks/detect/run \
  -F "file=@sample.png"
```

When multipart upload is inconvenient, use the generated base64 JSON endpoints:

```text
POST /v1/tasks/detect/run-base64
POST /v1/tasks/detect/jobs-base64
```

If an asynchronous job returns `FileResult`, download it directly:

```bash
curl -L http://127.0.0.1:8000/v1/jobs/JOB_ID/result-file -o report.txt
```

## SQLite job history

Jobs are kept in memory by default. For small LAN services that need status and results to survive
process restarts, pass a SQLite store:

```python
from aiserver import AIServer, SQLiteJobStore

server = AIServer("demo", job_store=SQLiteJobStore("jobs.sqlite3"))
```

Or enable it from the CLI without changing application code:

```bash
aiserver run app:server --jobs-db jobs.sqlite3
```

Queued or running jobs found after a restart are marked as interrupted. AIserver does not replay
unfinished model work.

## Lifecycle hooks

Keep large model objects in your application module and initialize them once:

```python
model = None


@server.on_startup
def load_model():
    global model
    model = load_your_model()


@server.on_shutdown
def release_model():
    global model
    model = None
```

AIserver is deliberately single-process so tasks can share an in-memory model. Without a
`job_store`, asynchronous job records stay in memory and are lost when the process restarts.

See [examples](docs/EXAMPLES.md) for OCR, image classification, YOLO detection, speech-to-text,
local embeddings, custom pipelines, and a LAN drone detector pattern.

List bundled examples from the CLI:

```bash
aiserver examples
aiserver version
```

## LAN access

The CLI refuses unauthenticated non-loopback binding by default. Set the token in the environment,
then start the server:

```powershell
$env:AISERVER_TOKEN = "use-a-long-random-value"
aiserver run app:server --host 0.0.0.0
```

Clients can use either header:

```text
Authorization: Bearer <token>
X-API-Key: <token>
```

Do not pass tokens on the command line or commit them to source control. Use a reverse proxy with
TLS before exposing AIserver outside a trusted private network.

## Scope

AIserver is not an LLM inference engine, OpenAI/Anthropic protocol gateway, model downloader,
distributed scheduler, or hosted control plane. Projects that need those capabilities should use
specialized runtimes and platforms.

## Historical package notice

Version `0.1.0` and newer are a clean rewrite. They do not preserve the unrelated remote-chat and robot demo
APIs from the historical `0.0.x` releases. Those releases should not be used.

## Development

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
ruff check .
pytest
python -m build
python -m twine check dist/*
```

## License

MIT
