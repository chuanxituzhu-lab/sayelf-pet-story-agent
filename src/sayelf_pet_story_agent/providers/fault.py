from __future__ import annotations

from .base import ProviderResult, VideoGenerationRequest, VideoProviderAdapter


class FaultVideoProvider:
    """Adapter wrapper that deterministically injects provider failures."""

    def __init__(
        self,
        delegate: VideoProviderAdapter,
        *,
        failures: int = 1,
        error_code: str = "PROVIDER_TIMEOUT",
        error_message: str = "simulated provider failure",
    ) -> None:
        if failures < 0:
            raise ValueError("failures must be non-negative")
        self.delegate = delegate
        self.failures = failures
        self.error_code = error_code
        self.error_message = error_message
        self.calls = 0
        self.name = f"fault({delegate.name})"

    def generate(self, request: VideoGenerationRequest) -> ProviderResult:
        self.calls += 1
        if self.calls <= self.failures:
            return ProviderResult(
                success=False,
                provider_name=self.name,
                error_code=self.error_code,
                error_message=self.error_message,
            )
        return self.delegate.generate(request)
