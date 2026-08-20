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
- Run tasks directly or submit in-memory asynchronous jobs.
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

Until `0.1.0` is available on PyPI, install the wheel from the GitHub Release or build from source.

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

AIserver is deliberately single-process so tasks can share an in-memory model. Its asynchronous
job records are not persistent and are lost when the process restarts.

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

Version `0.1.0` is a clean rewrite. It does not preserve the unrelated remote-chat and robot demo
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
