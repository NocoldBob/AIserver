"""LAN-only drone detection service sample.

Run on a trusted LAN with:
    $env:AISERVER_TOKEN = "use-a-long-random-value"
    aiserver run examples.drone_lan_detector:server --host 0.0.0.0
"""

from __future__ import annotations

import os

from aiserver import AIServer, InputFile, SQLiteJobStore, TaskContext

server = AIServer(
    "drone-lan-detector",
    max_request_bytes=20 * 1024 * 1024,
    job_store=SQLiteJobStore("jobs/drone-lan-detector.sqlite3"),
)
detector = None


@server.on_startup
def load_detector() -> None:
    """Load the local detector once.

    Keep model paths local to the machine through environment variables. Do not
    commit weights, credentials, board passwords, or private deployment paths.
    """

    global detector
    detector = {
        "model": os.getenv("DRONE_DETECTOR_MODEL", ""),
        "device": os.getenv("DRONE_DETECTOR_DEVICE", "cuda:0"),
    }


@server.file_task(concurrency=1, timeout=5, max_file_bytes=8 * 1024 * 1024)
def detect_frame(frame: InputFile, context: TaskContext) -> dict[str, object]:
    """Run one frame through a local drone detector."""

    context.report(0.2, "received frame")
    context.report(0.6, "running single-GPU detector")
    context.report(0.9, "postprocessing boxes")
    return {
        "filename": frame.filename,
        "content_type": frame.content_type,
        "detections": [],
        "model_configured": bool(detector and detector["model"]),
        "device": detector["device"] if detector else "cuda:0",
    }
