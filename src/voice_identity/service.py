"""Voice Identity service interface scaffold.

Not implemented yet.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    FingerprintGenerationRequest,
    FingerprintGenerationResult,
    SpeakerAttributionRequest,
    SpeakerAttributionResult,
)


class VoiceIdentityService(Protocol):
    """Facade contract for fingerprint generation and speaker attribution."""

    def generate_fingerprint(
        self,
        request: FingerprintGenerationRequest,
    ) -> FingerprintGenerationResult:
        """Generate a durable fingerprint.

        Not implemented yet.
        """

    def attribute_speaker(
        self,
        request: SpeakerAttributionRequest,
    ) -> SpeakerAttributionResult:
        """Resolve runtime speaker attribution.

        Not implemented yet.
        """


class NotImplementedVoiceIdentityService:
    """Placeholder service used until implementation work begins."""

    def generate_fingerprint(
        self,
        request: FingerprintGenerationRequest,
    ) -> FingerprintGenerationResult:
        raise NotImplementedError("VoiceIdentityService.generate_fingerprint is not implemented yet.")

    def attribute_speaker(
        self,
        request: SpeakerAttributionRequest,
    ) -> SpeakerAttributionResult:
        raise NotImplementedError("VoiceIdentityService.attribute_speaker is not implemented yet.")
