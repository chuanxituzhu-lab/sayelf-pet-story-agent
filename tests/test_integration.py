import unittest

from sayelf_pet_story_agent.application.service import PilotService
from sayelf_pet_story_agent.infrastructure.ledger import AppendOnlyEventLedger
from sayelf_pet_story_agent.providers.fault import FaultVideoProvider
from sayelf_pet_story_agent.providers.mock import MockVideoProvider


class PilotIntegrationTests(unittest.TestCase):
    def test_pilot_01_golden_path(self) -> None:
        ledger = AppendOnlyEventLedger()
        result = PilotService(ledger, MockVideoProvider()).run_pilot_01()
        self.assertTrue(result.ready)
        self.assertEqual(result.fixture.event.name, "Pet Expo Pilot 01")
        self.assertEqual(result.fixture.exhibitor.name, "HappyPet")
        self.assertEqual(result.fixture.product.name, "Smart Motion Ball")
        self.assertEqual(result.fixture.campaign.name, "My Pet Movie")
        self.assertEqual(len(result.fixture.shots), 8)
        self.assertEqual(ledger.all()[-1].event_type, "session.completed")

    def test_provider_fault_stops_before_video_ready(self) -> None:
        ledger = AppendOnlyEventLedger()
        provider = FaultVideoProvider(MockVideoProvider(), failures=1)
        result = PilotService(ledger, provider).run_pilot_01()
        self.assertFalse(result.ready)
        self.assertIsNone(result.video)
        self.assertEqual(result.error_code, "PROVIDER_TIMEOUT")
        self.assertEqual(ledger.all()[-1].event_type, "job.retryable")
