from __future__ import annotations

from dataclasses import dataclass

from pet_fde.domain.models import (
    GenerationAttempt,
    GenerationAttemptStatus,
    HallPlay,
    HallPlayStatus,
    JobStatus,
    Share,
    SessionStatus,
    ShareStatus,
    Video,
    VideoStatus,
)
from pet_fde.domain.state_machine import JobStateMachine, SessionStateMachine
from pet_fde.fixtures.pilot_01 import PilotFixture, build_pilot_01
from pet_fde.infrastructure.ledger import AppendOnlyEventLedger
from pet_fde.providers.base import VideoGenerationRequest, VideoProviderAdapter


@dataclass(frozen=True)
class PilotRunResult:
    fixture: PilotFixture
    video: Video | None
    share: Share | None
    hall_play: HallPlay | None
    ready: bool
    error_code: str | None = None


class PilotService:
    """Small orchestration slice proving the Sprint 01 contracts."""

    def __init__(self, ledger: AppendOnlyEventLedger, provider: VideoProviderAdapter) -> None:
        self.ledger = ledger
        self.provider = provider
        self.sessions = SessionStateMachine()
        self.jobs = JobStateMachine()

    def run_pilot_01(self) -> PilotRunResult:
        fixture = build_pilot_01()
        session = fixture.session
        job = fixture.job

        self._record("Session", session.id, "session.created", {"status": session.status.value})
        self.sessions.transition(session, SessionStatus.ACTIVE)
        self._record("Session", session.id, "session.active", {"status": session.status.value})

        self.jobs.transition(job, JobStatus.QUEUED)
        self._record("Job", job.id, "job.queued", {"status": job.status.value})
        self.jobs.transition(job, JobStatus.RUNNING)
        self._record("Job", job.id, "job.running", {"status": job.status.value})

        request = VideoGenerationRequest(
            job_id=job.id,
            shot_ids=tuple(shot.id for shot in fixture.shots),
            aspect_ratio="9:16",
        )
        attempt = GenerationAttempt(
            "attempt-pilot-01-001",
            job.id,
            1,
            self.provider.name,
            GenerationAttemptStatus.RUNNING,
        )
        self._record("GenerationAttempt", attempt.id, "generation.started", {"attempt_no": 1})
        result = self.provider.generate(request)
        if not result.success:
            self.jobs.transition(job, JobStatus.RETRYABLE)
            self._record(
                "GenerationAttempt",
                attempt.id,
                "generation.failed",
                {"error_code": result.error_code, "status": GenerationAttemptStatus.FAILED.value},
            )
            self._record("Job", job.id, "job.retryable", {"status": job.status.value})
            return PilotRunResult(fixture, None, None, None, False, result.error_code)

        self.jobs.transition(job, JobStatus.SUCCEEDED)
        video = Video(
            "video-pilot-01-001",
            job.id,
            request.aspect_ratio,
            VideoStatus.READY,
            result.provider_ref,
            result.local_path,
        )
        share = Share("share-pilot-01-001", video.id, "download", ShareStatus.READY)
        hall_play = HallPlay("hall-play-pilot-01-001", video.id, fixture.exhibitor.booth_code, HallPlayStatus.ELIGIBLE)
        self._record(
            "GenerationAttempt",
            attempt.id,
            "generation.succeeded",
            {"status": GenerationAttemptStatus.SUCCEEDED.value},
        )
        self._record("Job", job.id, "job.succeeded", {"status": job.status.value})
        self._record("Video", video.id, "video.ready", {"aspect_ratio": video.aspect_ratio})
        self._record("Share", share.id, "share.ready", {"channel": share.channel})
        self._record("HallPlay", hall_play.id, "hall.play.eligible", {"booth_code": hall_play.booth_code})
        self.sessions.transition(session, SessionStatus.COMPLETED)
        self._record("Session", session.id, "session.completed", {"status": session.status.value})
        return PilotRunResult(fixture, video, share, hall_play, True)

    def _record(self, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict[str, object]) -> None:
        self.ledger.append(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
