"""Internal model scaffolding for Voice Identity.

No production model/inference implementation is provided yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FingerprintArtifactRef:
    """Opaque reference to a provider-owned fingerprint artifact."""

    fingerprint_ref: str
    schema_version: int
    provider: str


@dataclass(slots=True)
class FingerprintModelIdentity:
    """Describes model identity used to generate a fingerprint."""

    model_name: str
    model_version: str
    algorithm: str
    dimension: int
