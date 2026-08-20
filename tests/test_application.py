from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from aiserver import AIServer, TaskContext


def _wait_for_terminal(client: TestClient, job_id: str, headers: dict[str, str] | None = None):
    for _ in range(100):
        response = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        body = response.json()
        if body["state"] in {"succeeded", "failed", "timed_out"}:
            return body
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_typed_direct_task_and_openapi() -> None:
    server = AIServer("test")

    @server.task(concurrency=2)
    def add(a: int, b: int = 1) -> int:
        return a + b

    with TestClient(server.app) as client:
        response = client.post("/v1/tasks/add/run", json={"a": 4})
        assert response.status_code == 200
        assert response.json()["result"] == 5

        invalid = client.post("/v1/tasks/add/run", json={"a": "wrong", "extra": 1})
        assert invalid.status_code == 422

        schema = client.get("/openapi.json").json()
        input_schema = schema["components"]["schemas"]["AddInput"]
        assert input_schema["required"] == ["a"]
        assert input_schema["properties"]["a"]["type"] == "integer"


def test_token_authentication_and_public_health() -> None:
    server = AIServer(token="top-secret")

    @server.task()
    def echo(value: str) -> str:
        return value

    with TestClient(server.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/tasks").status_code == 401
        headers = {"Authorization": "Bearer top-secret"}
        response = client.post("/v1/tasks/echo/run", json={"value": "ok"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["result"] == "ok"


def test_async_job_progress_and_result() -> None:
    server = AIServer()

    @server.task(timeout=2)
    def infer(value: str, context: TaskContext) -> dict[str, str]:
        context.report(0.5, "working")
        return {"value": value.upper()}

    with TestClient(server.app) as client:
        accepted = client.post("/v1/tasks/infer/jobs", json={"value": "hello"})
        assert accepted.status_code == 202
        body = _wait_for_terminal(client, accepted.json()["id"])
        assert body["state"] == "succeeded"
        assert body["progress"] == 1.0
        assert body["result"] == {"value": "HELLO"}


def test_job_timeout_hides_late_result() -> None:
    server = AIServer()

    @server.task(timeout=0.01)
    async def slow() -> str:
        import asyncio

        await asyncio.sleep(0.1)
        return "late"

    with TestClient(server.app) as client:
        accepted = client.post("/v1/tasks/slow/jobs", json={})
        body = _wait_for_terminal(client, accepted.json()["id"])
        assert body["state"] == "timed_out"
        assert body["result"] is None
        assert body["error"]["code"] == "timeout"


def test_concurrency_limit_is_enforced() -> None:
    server = AIServer()
    lock = threading.Lock()
    active = 0
    peak = 0

    @server.task(concurrency=1, timeout=2)
    def limited(value: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return value

    with TestClient(server.app) as client:
        first = client.post("/v1/tasks/limited/jobs", json={"value": 1}).json()["id"]
        second = client.post("/v1/tasks/limited/jobs", json={"value": 2}).json()["id"]
        assert _wait_for_terminal(client, first)["result"] == 1
        assert _wait_for_terminal(client, second)["result"] == 2
        assert peak == 1


def test_request_size_limit_and_lifecycle_hooks() -> None:
    events: list[str] = []
    server = AIServer(max_request_bytes=32)

    @server.on_startup
    def startup() -> None:
        events.append("start")

    @server.on_shutdown
    async def shutdown() -> None:
        events.append("stop")

    @server.task()
    def echo(value: str) -> str:
        return value

    with TestClient(server.app) as client:
        response = client.post("/v1/tasks/echo/run", json={"value": "x" * 100})
        assert response.status_code == 413
        assert events == ["start"]
    assert events == ["start", "stop"]
