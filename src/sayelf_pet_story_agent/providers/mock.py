from __future__ import annotations

from .base import ProviderResult, VideoGenerationRequest


class MockVideoProvider:
    """Deterministic local provider used by the Sprint 01 golden path."""

    name = "mock"

    def __init__(self) -> None:
        self.requests: list[VideoGenerationRequest] = []

    def generate(self, request: VideoGenerationRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            success=True,
            provider_name=self.name,
            provider_ref=f"mock:{request.job_id}",
            local_path=f"memory://videos/{request.job_id}.mp4",
        )
