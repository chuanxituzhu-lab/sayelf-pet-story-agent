from __future__ import annotations

from typing import Generic, TypeVar

from .models import Job, JobStatus, Session, SessionStatus


class InvalidTransition(ValueError):
    """Raised when a state change is not in the explicit transition table."""

    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(f"illegal {entity} transition: {current} -> {target}")
        self.entity = entity
        self.current = current
        self.target = target


T = TypeVar("T")


class _StateMachine(Generic[T]):
    entity_name: str
    transitions: dict[object, frozenset[object]]

    def _transition(self, entity: T, target: object, current: object) -> T:
        allowed = self.transitions.get(current, frozenset())
        if target not in allowed:
            raise InvalidTransition(
                self.entity_name,
                getattr(current, "value", str(current)),
                getattr(target, "value", str(target)),
            )
        return entity


class SessionStateMachine(_StateMachine[Session]):
    entity_name = "session"
    transitions = {
        SessionStatus.CREATED: frozenset({SessionStatus.ACTIVE, SessionStatus.ABANDONED}),
        SessionStatus.ACTIVE: frozenset({SessionStatus.COMPLETED, SessionStatus.ABANDONED}),
        SessionStatus.COMPLETED: frozenset(),
        SessionStatus.ABANDONED: frozenset(),
    }

    def transition(self, session: Session, target: SessionStatus) -> Session:
        self._transition(session, target, session.status)
        session.status = target
        return session


class JobStateMachine(_StateMachine[Job]):
    entity_name = "job"
    transitions = {
        JobStatus.CREATED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
        JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
        JobStatus.RUNNING: frozenset(
            {JobStatus.SUCCEEDED, JobStatus.RETRYABLE, JobStatus.FAILED, JobStatus.CANCELLED}
        ),
        JobStatus.RETRYABLE: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
        JobStatus.SUCCEEDED: frozenset(),
        JobStatus.FAILED: frozenset(),
        JobStatus.CANCELLED: frozenset(),
    }

    def transition(self, job: Job, target: JobStatus) -> Job:
        self._transition(job, target, job.status)
        job.status = target
        return job
