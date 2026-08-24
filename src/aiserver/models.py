"""Public response models."""

from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class InputFile(BaseModel):
    """File content supplied to a file task."""

    data: bytes
    filename: str | None = None
    content_type: str | None = None


class Base64FileInput(StrictInputModel):
    """JSON request body for file tasks when multipart upload is inconvenient."""

    data_base64: str
    filename: str | None = None
    content_type: str | None = None

    @field_validator("data_base64")
    @classmethod
    def validate_base64(cls, value: str) -> str:
        try:
            b64decode(value, validate=True)
        except Exception as error:
            raise ValueError("data_base64 must be valid base64") from error
        return value

    def to_input_file(self) -> InputFile:
        return InputFile(
            data=b64decode(self.data_base64, validate=True),
            filename=self.filename,
            content_type=self.content_type,
        )


class FileResult(BaseModel):
    """Base64-encoded file returned from a task."""

    data_base64: str
    filename: str | None = None
    content_type: str = "application/octet-stream"
    encoding: str = "base64"

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        filename: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> FileResult:
        return cls(
            data_base64=b64encode(data).decode("ascii"),
            filename=filename,
            content_type=content_type,
        )


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
