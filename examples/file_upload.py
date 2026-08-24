"""Run with: aiserver run examples.file_upload:server"""

from __future__ import annotations

from aiserver import AIServer, InputFile, TaskContext

server = AIServer("AIserver file upload example")


@server.file_task(concurrency=1, timeout=30)
def inspect_image(
    image: InputFile,
    context: TaskContext,
) -> dict[str, object]:
    """Accept one uploaded image and return lightweight inspection metadata."""

    context.report(0.25, "received upload")
    if image.data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif image.data.startswith(b"\xff\xd8\xff"):
        kind = "jpeg"
    elif image.data.startswith(b"GIF87a") or image.data.startswith(b"GIF89a"):
        kind = "gif"
    else:
        kind = "unknown"

    context.report(0.75, "inspected header")
    return {
        "filename": image.filename,
        "content_type": image.content_type,
        "bytes": len(image.data),
        "kind": kind,
    }
