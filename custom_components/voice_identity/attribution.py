"""Speaker attribution engine scaffold.

Production speaker attribution is not implemented yet.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import SpeakerAttributionRequest, SpeakerAttributionResult


class SpeakerAttributionEngine(Protocol):
    """Attributes incoming audio to enrolled voice profiles."""

    def attribute_speaker(self, request: SpeakerAttributionRequest) -> SpeakerAttributionResult:
        """Return speaker attribution result for one request."""


class NotImplementedSpeakerAttributionEngine:
    """Placeholder attribution engine used until implementation is added."""

    def attribute_speaker(self, request: SpeakerAttributionRequest) -> SpeakerAttributionResult:
        raise NotImplementedError("Speaker attribution is not implemented yet.")
