"""Public response models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictInputModel(BaseModel):
    """Base model used for generated task request bodies."""

    model_config = ConfigDict(extra="forbid")


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class TaskDescriptor(BaseModel):
    name: str
    description: str | None
    timeout_seconds: float | None
    concurrency: int
    input_schema: dict[str, Any]


class TaskExecutionResponse(BaseModel):
    task: str
    elapsed_seconds: float = Field(ge=0)
    result: Any


class JobAccepted(BaseModel):
    id: str
    task: str
    state: JobState
    status_url: str


class JobError(BaseModel):
    code: str
    message: str


class JobSnapshot(BaseModel):
    id: str
    task: str
    state: JobState
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    message: str | None = None
    result: Any = None
    error: JobError | None = None


class ServiceHealth(BaseModel):
    status: str
    name: str
    version: str
