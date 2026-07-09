"""Voice Identity service facade scaffold.

No runtime fingerprint or attribution engine is implemented yet.
"""

from __future__ import annotations

from .contracts import (
    FingerprintGenerationRequest,
    FingerprintGenerationResult,
    SpeakerAttributionRequest,
    SpeakerAttributionResult,
)


class VoiceIdentityService:
    """Facade contract exposed to integration consumers."""

    def generate_fingerprint(self, request: FingerprintGenerationRequest) -> FingerprintGenerationResult:
        raise NotImplementedError("VoiceIdentityService.generate_fingerprint is not implemented yet.")

    def attribute_speaker(self, request: SpeakerAttributionRequest) -> SpeakerAttributionResult:
        raise NotImplementedError("VoiceIdentityService.attribute_speaker is not implemented yet.")
