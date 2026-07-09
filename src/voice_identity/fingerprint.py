"""Fingerprint generation interface scaffold.

Not implemented yet.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import FingerprintGenerationRequest, FingerprintGenerationResult


class SpeakerFingerprintBuilder(Protocol):
    """Builds durable speaker fingerprint artifacts from enrollment samples."""

    def generate_fingerprint(
        self,
        request: FingerprintGenerationRequest,
    ) -> FingerprintGenerationResult:
        """Generate one fingerprint result from sample references.

        Not implemented yet.
        """


class NotImplementedSpeakerFingerprintBuilder:
    """Default placeholder builder used until engine implementation exists."""

    def generate_fingerprint(
        self,
        request: FingerprintGenerationRequest,
    ) -> FingerprintGenerationResult:
        raise NotImplementedError("Speaker fingerprint generation is not implemented yet.")
