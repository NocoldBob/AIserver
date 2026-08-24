"""Local embedding service skeleton.

Run with:
    aiserver run examples.embeddings:server
"""

from __future__ import annotations

import hashlib
import math

from aiserver import AIServer, TaskContext

server = AIServer("embeddings")
embedder = None


@server.on_startup
def load_embedder() -> None:
    """Load a local embedding model once."""

    global embedder
    embedder = "placeholder"


@server.task(concurrency=2, timeout=30)
def embed_text(text: str, context: TaskContext) -> dict[str, object]:
    """Return a deterministic placeholder vector for one text string."""

    context.report(0.4, "encoding text")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [byte / 255 for byte in digest[:16]]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    vector = [value / norm for value in values]
    return {"dimensions": len(vector), "embedding": vector}
