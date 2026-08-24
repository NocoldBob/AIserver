"""Optional job persistence backends."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import JobSnapshot


class SQLiteJobStore:
    """Persist job snapshots in a small local SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, snapshot: JobSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (id, task, state, created_at, finished_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task = excluded.task,
                    state = excluded.state,
                    created_at = excluded.created_at,
                    finished_at = excluded.finished_at,
                    payload = excluded.payload
                """,
                (
                    snapshot.id,
                    snapshot.task,
                    snapshot.state.value,
                    snapshot.created_at.isoformat(),
                    snapshot.finished_at.isoformat() if snapshot.finished_at else None,
                    payload,
                ),
            )

    def load(self, limit: int) -> list[JobSnapshot]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM jobs
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [JobSnapshot.model_validate(json.loads(row[0])) for row in rows]

    def delete(self, job_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
