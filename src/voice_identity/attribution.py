"""Speaker attribution interface scaffold.

Not implemented yet.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import SpeakerAttributionRequest, SpeakerAttributionResult


class SpeakerAttributionEngine(Protocol):
    """Resolves runtime speaker identity against stored fingerprints."""

    def attribute_speaker(
        self,
        request: SpeakerAttributionRequest,
    ) -> SpeakerAttributionResult:
        """Return runtime attribution result.

        Not implemented yet.
        """


class NotImplementedSpeakerAttributionEngine:
    """Default placeholder engine used until attribution implementation exists."""

    def attribute_speaker(
        self,
        request: SpeakerAttributionRequest,
    ) -> SpeakerAttributionResult:
        raise NotImplementedError("Speaker attribution is not implemented yet.")
