from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from dicomflow.core.timeutil import utc_now


class OutputFormat(str, Enum):
    MP4 = "mp4"
    GIF = "gif"


class Quality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JobPhase(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    DISCOVERING = "DISCOVERING"
    CONVERTING = "CONVERTING"
    PACKAGING = "PACKAGING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ConvertParams(BaseModel):
    format: OutputFormat = OutputFormat.MP4
    quality: Quality = Quality.HIGH
    merge: bool = False
    fps: int = Field(default=10, ge=1, le=30)
    deidentify: bool = True


class ProgressInfo(BaseModel):
    phase: JobPhase = JobPhase.PENDING
    percent: int = 0
    message: str = ""
    series_index: int | None = None
    series_total: int | None = None
    frame_index: int | None = None
    frame_total: int | None = None


class OutputArtifact(BaseModel):
    name: str
    kind: str  # series | merged | zip
    size_bytes: int | None = None
    content_type: str | None = None
    previewable: bool = False


class JobResult(BaseModel):
    download_name: str
    content_type: str
    size_bytes: int
    outputs: list[OutputArtifact] = Field(default_factory=list)


class JobError(BaseModel):
    code: str
    message: str
    detail: str | None = None


class UploadRecord(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    path: str
    created_at: datetime = Field(default_factory=utc_now)


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int


class JobStartRequest(BaseModel):
    upload_id: str
    format: OutputFormat = OutputFormat.MP4
    quality: Quality = Quality.HIGH
    merge: bool = False
    fps: int = Field(default=10, ge=1, le=30)


class JobRecord(BaseModel):
    job_id: str
    upload_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    params: ConvertParams = Field(default_factory=ConvertParams)
    progress: ProgressInfo = Field(default_factory=ProgressInfo)
    result: JobResult | None = None
    error: JobError | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    source_name: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: ProgressInfo
    result: JobResult | None = None
    error: JobError | None = None
    created_at: datetime
    updated_at: datetime
    source_name: str | None = None
    upload_id: str | None = None
