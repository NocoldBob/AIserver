"""Runnable AI-style demo without extra model dependencies.

Run with:
    aiserver run examples.runnable_demo:server
"""

from __future__ import annotations

import hashlib
import json
import math

from aiserver import AIServer, FileResult, InputFile, SQLiteJobStore, TaskContext

server = AIServer("runnable-demo", job_store=SQLiteJobStore("jobs/runnable-demo.sqlite3"))


@server.task(concurrency=2, timeout=10)
def embed_text(text: str, context: TaskContext) -> dict[str, object]:
    """Create a deterministic embedding-like vector."""

    context.report(0.3, "hashing text")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [byte / 255 for byte in digest[:16]]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return {"dimensions": len(values), "embedding": [value / norm for value in values]}


@server.file_task(concurrency=1, timeout=20, max_file_bytes=8 * 1024 * 1024)
def classify_image(image: InputFile, context: TaskContext) -> dict[str, object]:
    """Classify a file by lightweight image header inspection."""

    context.report(0.2, "checking file header")
    if image.data.startswith(b"\x89PNG"):
        label = "png-image"
    elif image.data.startswith(b"\xff\xd8\xff"):
        label = "jpeg-image"
    elif image.data.startswith(b"GIF87a") or image.data.startswith(b"GIF89a"):
        label = "gif-image"
    else:
        label = "unknown-file"
    return {
        "filename": image.filename,
        "content_type": image.content_type,
        "label": label,
        "confidence": 0.9 if label != "unknown-file" else 0.2,
    }


@server.file_task(concurrency=1, timeout=20, max_file_bytes=8 * 1024 * 1024)
def mock_ocr(image: InputFile, context: TaskContext) -> dict[str, object]:
    """Return OCR-style metadata from an uploaded image."""

    context.report(0.5, "extracting text-like metadata")
    return {
        "filename": image.filename,
        "text": f"Received {len(image.data)} bytes",
        "lines": [{"text": "placeholder OCR line", "confidence": 0.5}],
    }


@server.file_task(concurrency=1, timeout=20, max_file_bytes=8 * 1024 * 1024)
def summarize_file(document: InputFile, context: TaskContext) -> FileResult:
    """Generate a JSON report and return it as a downloadable file."""

    context.report(0.4, "building report")
    report = {
        "source": document.filename,
        "content_type": document.content_type,
        "bytes": len(document.data),
    }
    return FileResult.from_bytes(
        json.dumps(report, indent=2).encode("utf-8"),
        filename="summary.json",
        content_type="application/json",
    )
