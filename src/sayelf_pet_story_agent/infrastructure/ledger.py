from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from sayelf_pet_story_agent.domain.models import LedgerEvent, utc_now


class AppendOnlyEventLedger:
    """A small local JSONL ledger with append-only semantics."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._events: list[LedgerEvent] = []
        if self.path is not None and self.path.exists():
            self._load()

    def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> LedgerEvent:
        event = LedgerEvent(
            id=str(uuid4()),
            sequence=len(self._events) + 1,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=dict(payload),
            occurred_at=utc_now(),
        )
        self._events.append(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self._to_dict(event), ensure_ascii=False) + "\n")
        return event

    def all(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def for_aggregate(self, aggregate_id: str) -> tuple[LedgerEvent, ...]:
        return tuple(event for event in self._events if event.aggregate_id == aggregate_id)

    def _load(self) -> None:
        assert self.path is not None
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                expected = len(self._events) + 1
                if raw["sequence"] != expected:
                    raise ValueError("ledger sequence is not append-only")
                self._events.append(self._from_dict(raw))

    @staticmethod
    def _to_dict(event: LedgerEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "sequence": event.sequence,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "event_type": event.event_type,
            "payload": dict(event.payload),
            "occurred_at": event.occurred_at.isoformat(),
        }

    @staticmethod
    def _from_dict(raw: Mapping[str, Any]) -> LedgerEvent:
        from datetime import datetime

        return LedgerEvent(
            id=str(raw["id"]),
            sequence=int(raw["sequence"]),
            aggregate_type=str(raw["aggregate_type"]),
            aggregate_id=str(raw["aggregate_id"]),
            event_type=str(raw["event_type"]),
            payload=dict(raw["payload"]),
            occurred_at=datetime.fromisoformat(str(raw["occurred_at"])),
        )
