"""Integration-local contract scaffolding for Voice Identity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class FingerprintGenerationRequest:
    voice_profile_id: str
    person_id: str | None = None
    sample_refs: list[str] = field(default_factory=list)
    expected_sample_count: int = 0
    model_preference: str = ""
    requested_at: str = field(default_factory=_utcnow_iso)


@dataclass(slots=True)
class FingerprintGenerationResult:
    success: bool
    fingerprint_ref: str = ""
    fingerprint_schema_version: int = 1
    fingerprint_model: str = ""
    fingerprint_model_version: str = ""
    fingerprint_dimension: int = 0
    fingerprint_quality_score: float | None = None
    fingerprint_sample_count: int = 0
    failure_code: str = ""
    failure_message_safe: str = ""


@dataclass(slots=True)
class SpeakerAttributionRequest:
    audio_ref: str = ""
    audio_bytes: bytes | None = None
    candidate_scope: list[str] = field(default_factory=list)
    model_preference: str = ""
    requested_at: str = field(default_factory=_utcnow_iso)


@dataclass(slots=True)
class SpeakerAttributionResult:
    matched: bool
    person_id: str | None = None
    voice_profile_id: str | None = None
    speaker_match_confidence: float | None = None
    threshold: float | None = None
    reason_code: str = ""
    failure_message_safe: str = ""
