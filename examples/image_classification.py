"""Image classification service skeleton.

Run with:
    aiserver run examples.image_classification:server
"""

from __future__ import annotations

from aiserver import AIServer, InputFile, TaskContext

server = AIServer("image-classifier")
model = None


@server.on_startup
def load_model() -> None:
    """Load a local classifier once per process.

    Replace the placeholder with your own PyTorch, ONNX Runtime, TensorRT, or
    OpenCV model initialization.
    """

    global model
    model = {"labels": ["unknown", "document", "scene", "object"]}


@server.on_shutdown
def release_model() -> None:
    global model
    model = None


@server.file_task(concurrency=1, timeout=30, max_file_bytes=8 * 1024 * 1024)
def classify_image(image: InputFile, context: TaskContext) -> dict[str, object]:
    """Classify one uploaded image."""

    context.report(0.2, "preprocessing image")
    if image.data.startswith(b"\x89PNG"):
        label = "document"
    elif image.data.startswith(b"\xff\xd8\xff"):
        label = "scene"
    else:
        label = "unknown"
    context.report(0.9, "formatting result")
    return {
        "filename": image.filename,
        "content_type": image.content_type,
        "label": label,
        "confidence": 0.5 if label == "unknown" else 0.82,
    }
