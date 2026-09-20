import unittest

from sayelf_pet_story_agent.domain.models import Job, JobStatus, Session, SessionStatus, VideoMode
from sayelf_pet_story_agent.domain.state_machine import InvalidTransition, JobStateMachine, SessionStateMachine


class StateMachineTests(unittest.TestCase):
    def test_session_golden_path_and_illegal_transition(self) -> None:
        session = Session("s1", "e1")
        machine = SessionStateMachine()
        machine.transition(session, SessionStatus.ACTIVE)
        machine.transition(session, SessionStatus.COMPLETED)
        self.assertEqual(session.status, SessionStatus.COMPLETED)
        with self.assertRaises(InvalidTransition):
            machine.transition(session, SessionStatus.ACTIVE)
        self.assertEqual(session.status, SessionStatus.COMPLETED)

    def test_job_retry_path_and_terminal_guard(self) -> None:
        job = Job("j1", "s1", VideoMode.ANIMATION)
        machine = JobStateMachine()
        for status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYABLE, JobStatus.QUEUED, JobStatus.RUNNING):
            machine.transition(job, status)
        machine.transition(job, JobStatus.SUCCEEDED)
        with self.assertRaises(InvalidTransition):
            machine.transition(job, JobStatus.QUEUED)
