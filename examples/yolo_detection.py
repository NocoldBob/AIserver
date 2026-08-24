"""YOLO object detection service skeleton.

Run with:
    aiserver run examples.yolo_detection:server
"""

from __future__ import annotations

import os

from aiserver import AIServer, InputFile, TaskContext

server = AIServer("yolo-detector")
detector = None


@server.on_startup
def load_detector() -> None:
    """Load a YOLO model from a local path.

    Set YOLO_MODEL_PATH to a local .pt, .onnx, or TensorRT engine path and
    replace the placeholder with your preferred runtime.
    """

    global detector
    detector = {"model_path": os.getenv("YOLO_MODEL_PATH")}


@server.file_task(concurrency=1, timeout=45, max_file_bytes=16 * 1024 * 1024)
def detect_objects(image: InputFile, context: TaskContext) -> dict[str, object]:
    """Detect objects in one uploaded image."""

    context.report(0.25, "preprocessing frame")
    context.report(0.75, "running detector")
    return {
        "filename": image.filename,
        "detections": [],
        "model_path_configured": bool(detector and detector.get("model_path")),
    }
