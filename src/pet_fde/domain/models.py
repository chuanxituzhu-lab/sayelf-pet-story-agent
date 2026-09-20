from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EntrySource(str, Enum):
    BOOTH_QR = "booth_qr"
    HALL_QR = "hall_qr"
    SHARE_REFERRAL = "share_referral"


class VideoMode(str, Enum):
    ANIMATION = "animation"
    CINEMATIC = "cinematic"


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    RETRYABLE = "retryable"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationAttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VideoStatus(str, Enum):
    READY = "ready"
    FAILED = "failed"


class ShareStatus(str, Enum):
    READY = "ready"
    REVOKED = "revoked"


class HallPlayStatus(str, Enum):
    ELIGIBLE = "eligible"
    PLAYED = "played"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    venue: str


@dataclass(frozen=True)
class Exhibitor:
    id: str
    event_id: str
    name: str
    booth_code: str


@dataclass(frozen=True)
class Product:
    id: str
    exhibitor_id: str
    name: str


@dataclass(frozen=True)
class Campaign:
    id: str
    event_id: str
    exhibitor_id: str
    product_id: str
    name: str
    primary_goal: str
    secondary_goal: str


@dataclass(frozen=True)
class Entry:
    id: str
    campaign_id: str
    source: EntrySource
    input_text: str
    hall_consent: bool = False


@dataclass
class Session:
    id: str
    entry_id: str
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class Pet:
    id: str
    session_id: str
    description: str
    photo_ref: str | None = None


@dataclass
class Job:
    id: str
    session_id: str
    mode: VideoMode
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class Shot:
    id: str
    job_id: str
    sequence: int
    name: str


@dataclass(frozen=True)
class GenerationAttempt:
    id: str
    job_id: str
    attempt_no: int
    provider_name: str
    status: GenerationAttemptStatus
    error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class Video:
    id: str
    job_id: str
    aspect_ratio: str
    status: VideoStatus
    provider_ref: str | None = None
    local_path: str | None = None


@dataclass(frozen=True)
class Share:
    id: str
    video_id: str
    channel: str
    status: ShareStatus = ShareStatus.READY
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class HallPlay:
    id: str
    video_id: str
    booth_code: str
    status: HallPlayStatus = HallPlayStatus.ELIGIBLE


@dataclass(frozen=True)
class LedgerEvent:
    id: str
    sequence: int
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Mapping[str, Any]
    occurred_at: datetime = field(default_factory=utc_now)
