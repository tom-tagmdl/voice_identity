"""Voice Identity package scaffold.

This package currently provides contract and interface stubs only.
No production fingerprint or attribution engine is implemented yet.
"""

from .contracts import (
    FingerprintGenerationRequest,
    FingerprintGenerationResult,
    SpeakerAttributionRequest,
    SpeakerAttributionResult,
)

__all__ = [
    "FingerprintGenerationRequest",
    "FingerprintGenerationResult",
    "SpeakerAttributionRequest",
    "SpeakerAttributionResult",
]
