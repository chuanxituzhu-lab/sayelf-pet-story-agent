from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VideoGenerationRequest:
    job_id: str
    shot_ids: tuple[str, ...]
    aspect_ratio: str


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider_name: str
    provider_ref: str | None = None
    local_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class VideoProviderAdapter(Protocol):
    name: str

    def generate(self, request: VideoGenerationRequest) -> ProviderResult:
        ...
