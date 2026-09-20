from __future__ import annotations

from sayelf_pet_story_agent.application.service import PilotService
from sayelf_pet_story_agent.infrastructure.ledger import AppendOnlyEventLedger
from sayelf_pet_story_agent.providers.mock import MockVideoProvider


def main() -> None:
    result = PilotService(AppendOnlyEventLedger(), MockVideoProvider()).run_pilot_01()
    if not result.ready:
        print("sayelf-pet-story-agent Pilot 01: NOT READY")
        return
    print("sayelf-pet-story-agent Pilot 01: READY")
    print(f"Event: {result.fixture.event.name}")
    print(f"Campaign: {result.fixture.campaign.name}")
    print(f"Story shots: {len(result.fixture.shots)}")
    print("Session: completed")
    print("Video: ready")
    print("Share: ready")
    print("Hall play: eligible")


if __name__ == "__main__":
    main()
