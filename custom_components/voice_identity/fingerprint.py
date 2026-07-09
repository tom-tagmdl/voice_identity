"""Fingerprint builder scaffold.

Production fingerprint generation is not implemented yet.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import FingerprintGenerationRequest, FingerprintGenerationResult


class SpeakerFingerprintBuilder(Protocol):
    """Builds durable speaker fingerprint artifacts."""

    def generate_fingerprint(self, request: FingerprintGenerationRequest) -> FingerprintGenerationResult:
        """Generate a fingerprint from enrollment sample references."""


class NotImplementedSpeakerFingerprintBuilder:
    """Placeholder builder used until implementation is added."""

    def generate_fingerprint(self, request: FingerprintGenerationRequest) -> FingerprintGenerationResult:
        raise NotImplementedError("Speaker fingerprint generation is not implemented yet.")
