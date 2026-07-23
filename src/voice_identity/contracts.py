"""Public Voice Identity contracts.

These are scaffold contracts and may evolve through architecture decisions.
No model runtime is implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


RUNTIME_IDENTITY_REASON_CODES: tuple[str, ...] = (
    "identity_known_high_confidence",
    "identity_known_medium_confidence",
    "identity_known_low_confidence",
    "identity_ambiguous_match",
    "identity_unknown",
    "identity_unavailable",
    "identity_audio_missing",
    "identity_context_missing",
    "identity_context_stale",
    "identity_context_expired",
    "identity_not_required",
    "identity_required_but_missing",
    "identity_required_fresh_but_stale",
    "identity_policy_blocked_sensitive_intent",
    "identity_step_up_required",
)


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
    conversation_id: str | None = None
    device_id: str | None = None
    satellite_id: str | None = None
    room_id: str | None = None
    turn_index: int | None = None
    pipeline_id: str | None = None
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


@dataclass(slots=True, frozen=True)
class IdentityContext:
    state: str
    person_id: str | None = None
    voice_profile_id: str | None = None
    confidence: float | None = None
    confidence_band: str | None = None
    reason_code: str | None = None
    source: str = "voice_identity"
    generated_at: str = field(default_factory=_utcnow_iso)


def _parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compute_default_attribution_ttl_seconds(*, state: str, confidence_band: str | None) -> int:
    normalized_state = str(state or "").strip().lower()
    normalized_band = str(confidence_band or "").strip().lower()

    if normalized_state in {"unknown", "unavailable"}:
        return 0
    if normalized_state == "not_required":
        return 10
    if normalized_state == "ambiguous" or normalized_band in {"ambiguous", "low"}:
        return 5
    if normalized_band == "medium":
        return 15
    if normalized_band == "high":
        return 30
    return 15


def _cap_expiry(*, issued_at_utc: str, expires_at_utc: str, max_seconds: int = 60) -> str:
    issued = _parse_utc_iso(issued_at_utc)
    expires = _parse_utc_iso(expires_at_utc)
    hard_cap = issued + timedelta(seconds=max_seconds)
    return min(expires, hard_cap).isoformat()


@dataclass(slots=True, frozen=True)
class AttributionBinding:
    conversation_id: str | None = None
    device_id: str | None = None
    satellite_id: str | None = None
    pipeline_id: str | None = None
    turn_index: int | None = None
    room_id: str | None = None


@dataclass(slots=True, frozen=True)
class AttributionSubject:
    person_id: str | None = None
    display_name: str | None = None
    profile_id: str | None = None


@dataclass(slots=True, frozen=True)
class AttributionConfidence:
    score: float | None = None
    band: str = "none"


@dataclass(slots=True, frozen=True)
class AttributionDecision:
    state: str
    reason_code: str
    recommended_action: str


@dataclass(slots=True, frozen=True)
class AttributionFreshness:
    attribution_age_ms: int
    valid_until_utc: str
    freshness_class: str


@dataclass(slots=True, frozen=True)
class AttributionDiagnostics:
    model_version: str | None = None
    attribution_latency_ms: int | None = None
    evidence_flags: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class AttributionIntegrity:
    signature_present: bool = False
    nonce_present: bool = False


@dataclass(slots=True, frozen=True)
class RuntimeAttributionRecord:
    contract_version: str
    attribution_id: str
    issued_at_utc: str
    expires_at_utc: str
    producer: str
    binding: AttributionBinding
    subject: AttributionSubject
    confidence: AttributionConfidence
    decision: AttributionDecision
    freshness: AttributionFreshness
    diagnostics: AttributionDiagnostics
    integrity: AttributionIntegrity

    def normalized(self) -> "RuntimeAttributionRecord":
        return RuntimeAttributionRecord(
            contract_version=self.contract_version,
            attribution_id=self.attribution_id,
            issued_at_utc=self.issued_at_utc,
            expires_at_utc=_cap_expiry(
                issued_at_utc=self.issued_at_utc,
                expires_at_utc=self.expires_at_utc,
            ),
            producer=self.producer,
            binding=self.binding,
            subject=self.subject,
            confidence=self.confidence,
            decision=self.decision,
            freshness=self.freshness,
            diagnostics=self.diagnostics,
            integrity=self.integrity,
        )
