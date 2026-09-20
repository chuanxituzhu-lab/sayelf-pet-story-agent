import tempfile
import unittest
from pathlib import Path

from sayelf_pet_story_agent.infrastructure.ledger import AppendOnlyEventLedger


class LedgerTests(unittest.TestCase):
    def test_jsonl_round_trip_preserves_append_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            ledger = AppendOnlyEventLedger(path)
            ledger.append(aggregate_type="Job", aggregate_id="j1", event_type="job.created", payload={"x": 1})
            ledger.append(aggregate_type="Job", aggregate_id="j1", event_type="job.running", payload={"x": 2})
            restored = AppendOnlyEventLedger(path)
            self.assertEqual([event.sequence for event in restored.all()], [1, 2])
            self.assertEqual([event.event_type for event in restored.for_aggregate("j1")], ["job.created", "job.running"])

    def test_ledger_has_no_mutation_api(self) -> None:
        ledger = AppendOnlyEventLedger()
        self.assertFalse(hasattr(ledger, "update"))
        self.assertFalse(hasattr(ledger, "delete"))
