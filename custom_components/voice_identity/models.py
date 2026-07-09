"""Model scaffolding for Voice Identity integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FingerprintArtifactRef:
    """Opaque reference to a fingerprint artifact owned by storage provider."""

    fingerprint_ref: str
    schema_version: int
    provider: str


@dataclass(slots=True)
class FingerprintStatus:
    """High-level status projection for scaffold diagnostics."""

    status: str = "not_implemented"
    message: str = "Voice Identity runtime is not implemented yet."
