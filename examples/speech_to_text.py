"""Speech-to-text service skeleton.

Run with:
    aiserver run examples.speech_to_text:server
"""

from __future__ import annotations

from aiserver import AIServer, InputFile, TaskContext

server = AIServer("speech-to-text")
transcriber = None


@server.on_startup
def load_transcriber() -> None:
    """Load a local speech model once.

    This is where you would initialize faster-whisper, Whisper.cpp bindings, or
    another local ASR runtime.
    """

    global transcriber
    transcriber = "placeholder"


@server.file_task(concurrency=1, timeout=120, max_file_bytes=64 * 1024 * 1024)
def transcribe_audio(audio: InputFile, context: TaskContext) -> dict[str, object]:
    """Transcribe one uploaded audio file."""

    context.report(0.15, "reading audio")
    context.report(0.75, "running speech model")
    return {
        "filename": audio.filename,
        "content_type": audio.content_type,
        "text": "",
        "segments": [],
        "note": "Replace the placeholder body with a local speech model call.",
    }
