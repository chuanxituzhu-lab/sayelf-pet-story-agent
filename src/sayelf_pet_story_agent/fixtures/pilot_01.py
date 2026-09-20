from __future__ import annotations

from dataclasses import dataclass

from sayelf_pet_story_agent.domain.models import (
    Campaign,
    Entry,
    EntrySource,
    Event,
    Exhibitor,
    Job,
    Pet,
    Product,
    Session,
    Shot,
    VideoMode,
)


@dataclass(frozen=True)
class PilotFixture:
    event: Event
    exhibitor: Exhibitor
    product: Product
    campaign: Campaign
    entry: Entry
    session: Session
    pet: Pet
    job: Job
    shots: tuple[Shot, ...]


def build_pilot_01() -> PilotFixture:
    event = Event("event-pilot-01", "Pet Expo Pilot 01", "Pilot Hall")
    exhibitor = Exhibitor("exhibitor-happypet", event.id, "HappyPet", "A17")
    product = Product("product-smart-motion-ball", exhibitor.id, "Smart Motion Ball")
    campaign = Campaign(
        "campaign-my-pet-movie",
        event.id,
        exhibitor.id,
        product.id,
        "My Pet Movie",
        "Share / Referral",
        "Product Awareness",
    )
    entry = Entry(
        "entry-pilot-01-001",
        campaign.id,
        EntrySource.BOOTH_QR,
        "a white Persian cat",
        hall_consent=True,
    )
    session = Session("session-pilot-01-001", entry.id)
    pet = Pet("pet-pilot-01-001", session.id, entry.input_text)
    job = Job("job-pilot-01-001", session.id, VideoMode.ANIMATION)
    names = (
        "Discover",
        "Approach",
        "Contact",
        "Chase",
        "Victory",
        "False Resolution",
        "Reversal",
        "Reaction",
    )
    shots = tuple(
        Shot(f"shot-pilot-01-{index:03d}", job.id, index, name)
        for index, name in enumerate(names, start=1)
    )
    return PilotFixture(event, exhibitor, product, campaign, entry, session, pet, job, shots)
