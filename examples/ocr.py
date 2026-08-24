"""OCR service skeleton.

Run with:
    aiserver run examples.ocr:server
"""

from __future__ import annotations

from aiserver import AIServer, InputFile, TaskContext

server = AIServer("ocr")
ocr_engine = None


@server.on_startup
def load_ocr_engine() -> None:
    """Load an OCR engine once.

    For a real service, initialize PaddleOCR, EasyOCR, Tesseract, or your own
    OCR pipeline here. Keeping it behind a lifecycle hook prevents per-request
    model reloads.
    """

    global ocr_engine
    ocr_engine = "placeholder"


@server.file_task(concurrency=1, timeout=60, max_file_bytes=12 * 1024 * 1024)
def read_text(image: InputFile, context: TaskContext) -> dict[str, object]:
    """Extract text from one uploaded image."""

    context.report(0.2, "decoding image")
    context.report(0.7, "running OCR")
    return {
        "filename": image.filename,
        "text": "",
        "lines": [],
        "note": "Replace the placeholder body with a local OCR engine call.",
    }
