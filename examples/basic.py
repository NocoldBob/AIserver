"""Run with: aiserver run examples.basic:server"""

from __future__ import annotations

import time

from aiserver import AIServer, TaskContext

server = AIServer("AIserver example")


@server.task(concurrency=4, timeout=10)
def add(a: float, b: float) -> dict[str, float]:
    """Add two numbers."""

    return {"value": a + b}


@server.task(concurrency=1, timeout=30)
def simulated_inference(text: str, context: TaskContext) -> dict[str, str]:
    """Demonstrate a long-running, concurrency-limited inference job."""

    for step in range(5):
        time.sleep(0.2)
        context.report((step + 1) / 5, f"step {step + 1} of 5")
    return {"output": text.upper()}
