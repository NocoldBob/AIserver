"""Progress reporting for running jobs."""

from __future__ import annotations

from collections.abc import Callable


class TaskContext:
    """A task-local progress reporter injected by AIserver.

    Parameters annotated as ``TaskContext`` are omitted from the request schema and are
    supplied by the runtime. ``report`` is safe to call from synchronous worker threads.
    """

    def __init__(self, reporter: Callable[[float | None, str | None], None]) -> None:
        self._reporter = reporter

    def report(self, progress: float | None = None, message: str | None = None) -> None:
        """Update job progress.

        ``progress`` is a value from 0.0 through 1.0. Passing ``None`` leaves the current
        numeric progress unchanged while allowing the message to be updated.
        """

        if progress is not None and not 0.0 <= progress <= 1.0:
            raise ValueError("progress must be between 0.0 and 1.0")
        self._reporter(progress, message)
