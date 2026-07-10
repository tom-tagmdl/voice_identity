"""Speaker attribution foundation models.

These contracts are advisory and privacy-safe. Attribution provides evidence,
not identity truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .diagnostics_sanitizer import sanitize_mapping


class IdentityConfidenceLevel(StrEnum):
    """Identity confidence levels for downstream consumers."""

    UNKNOWN = "unknown"
    ASSERTED = "asserted"
    INFERRED = "inferred"
    RECOGNIZED = "recognized"


class AttributionStatus(StrEnum):
    """Attribution operation status surface."""

    READY = "attribution_ready"
    UNAVAILABLE = "attribution_unavailable"
    ABSTAINED = "attribution_abstained"


class AttributionMethod(StrEnum):
    """Attribution evidence source classification."""

    NONE = "none"
    VOICEPRINT_RECOGNITION = "voiceprint_recognition"


class ConfidenceBand(StrEnum):
    """Typed confidence bands for advisory attribution."""

    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    NO_MATCH = "no_match"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True, frozen=True)
class AttributionDiagnosticSummary:
    """Safe attribution diagnostic and readiness summary."""

    diagnostic_available: bool
    diagnostic_reason_code: str
    repair_available: bool
    health_status: str
    attribution_readiness: str
    compatibility_readiness: str


@dataclass(slots=True, frozen=True)
class AttributionResult:
    """Canonical advisory attribution result contract."""

    success: bool
    status: AttributionStatus
    identity_confidence_level: IdentityConfidenceLevel
    attributed_person_id: str | None
    attributed_profile_id: str | None
    attributed_artifact_id: str | None
    confidence: float
    confidence_band: ConfidenceBand
    reason_code: str
    attribution_method: AttributionMethod
    is_confident: bool
    is_ambiguous: bool
    is_abstained: bool
    diagnostic_summary: AttributionDiagnosticSummary
    repair_hint_code: str
    suggested_next_action_code: str
    health_status: str
    readiness_status: str

    def to_dict(self) -> dict[str, object]:
        """Serialize result as safe machine-readable payload."""
        payload = {
            "success": self.success,
            "status": self.status.value,
            "identity_confidence_level": self.identity_confidence_level.value,
            "attributed_person_id": self.attributed_person_id,
            "attributed_profile_id": self.attributed_profile_id,
            "attributed_artifact_id": self.attributed_artifact_id,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band.value,
            "reason_code": self.reason_code,
            "attribution_method": self.attribution_method.value,
            "is_confident": self.is_confident,
            "is_ambiguous": self.is_ambiguous,
            "is_abstained": self.is_abstained,
            "diagnostic_summary": {
                "diagnostic_available": self.diagnostic_summary.diagnostic_available,
                "diagnostic_reason_code": self.diagnostic_summary.diagnostic_reason_code,
                "repair_available": self.diagnostic_summary.repair_available,
                "health_status": self.diagnostic_summary.health_status,
                "attribution_readiness": self.diagnostic_summary.attribution_readiness,
                "compatibility_readiness": self.diagnostic_summary.compatibility_readiness,
            },
            "repair_hint_code": self.repair_hint_code,
            "suggested_next_action_code": self.suggested_next_action_code,
            "health_status": self.health_status,
            "readiness_status": self.readiness_status,
        }
        return sanitize_mapping(payload)
