"""Custom Python pipeline with a file result.

Run with:
    aiserver run examples.custom_pipeline:server
"""

from __future__ import annotations

import json

from aiserver import AIServer, FileResult, InputFile, TaskContext

server = AIServer("custom-pipeline")


@server.file_task(concurrency=1, timeout=45, max_file_bytes=16 * 1024 * 1024)
def summarize_file(document: InputFile, context: TaskContext) -> FileResult:
    """Read one file and return a generated JSON report as a file result."""

    context.report(0.3, "parsing input")
    report = {
        "source": document.filename,
        "content_type": document.content_type,
        "bytes": len(document.data),
        "pipeline": ["parse", "infer", "postprocess"],
    }
    context.report(0.9, "encoding report")
    return FileResult.from_bytes(
        json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
        filename="report.json",
        content_type="application/json",
    )
