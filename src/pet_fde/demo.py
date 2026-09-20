from __future__ import annotations

from pet_fde.application.service import PilotService
from pet_fde.infrastructure.ledger import AppendOnlyEventLedger
from pet_fde.providers.mock import MockVideoProvider


def main() -> None:
    result = PilotService(AppendOnlyEventLedger(), MockVideoProvider()).run_pilot_01()
    if not result.ready:
        print("Pet FDE Pilot 01: NOT READY")
        return
    print("Pet FDE Pilot 01: READY")
    print(f"Event: {result.fixture.event.name}")
    print(f"Campaign: {result.fixture.campaign.name}")
    print(f"Story shots: {len(result.fixture.shots)}")
    print("Session: completed")
    print("Video: ready")
    print("Share: ready")
    print("Hall play: eligible")


if __name__ == "__main__":
    main()
