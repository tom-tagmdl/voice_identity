"""Canonical Identity Context generation for Concierge-facing consumption.

Identity Context is behavioral context, not authentication or authorization.
"""

from __future__ import annotations

from dataclasses import asdict
from enum import StrEnum

from .attribution_models import AttributionResult, AttributionStatus, ConfidenceBand, IdentityConfidenceLevel
from .contracts import IdentityContext
from .diagnostics_sanitizer import normalize_reason_code, safe_token, sanitize_mapping


class IdentityContextState(StrEnum):
    """Stable identity context state surface."""

    KNOWN = "known"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"
    LOW_CONFIDENCE = "low_confidence"
    UNAVAILABLE = "unavailable"


class IdentityContextGenerator:
    """Generate canonical identity context from attribution outcomes."""

    def generate(self, *, attribution: AttributionResult) -> IdentityContext:
        """Project identity context state from one attribution result."""
        state = self._state_for(attribution)

        person_id: str | None = None
        voice_profile_id: str | None = None
        confidence: float | None = None
        confidence_band: str | None = None

        if state is IdentityContextState.KNOWN:
            person_id = _safe_id(attribution.attributed_person_id)
            voice_profile_id = _safe_id(attribution.attributed_profile_id)
            confidence = attribution.confidence
            confidence_band = attribution.confidence_band.value
        elif state is IdentityContextState.LOW_CONFIDENCE:
            confidence = attribution.confidence
            confidence_band = attribution.confidence_band.value

        reason_code = normalize_reason_code(attribution.reason_code)
        return IdentityContext(
            state=state.value,
            person_id=person_id,
            voice_profile_id=voice_profile_id,
            confidence=confidence,
            confidence_band=confidence_band,
            reason_code=reason_code,
            source="voice_identity",
        )

    def to_dict(self, *, context: IdentityContext) -> dict[str, object]:
        """Serialize identity context into safe payload."""
        return sanitize_mapping(asdict(context))

    def _state_for(self, attribution: AttributionResult) -> IdentityContextState:
        reason_code = normalize_reason_code(attribution.reason_code)

        if attribution.status is AttributionStatus.UNAVAILABLE:
            return IdentityContextState.UNAVAILABLE

        if attribution.status is AttributionStatus.READY:
            if (
                attribution.identity_confidence_level is IdentityConfidenceLevel.RECOGNIZED
                and _safe_id(attribution.attributed_profile_id)
            ):
                return IdentityContextState.KNOWN
            return IdentityContextState.UNKNOWN

        if attribution.status is AttributionStatus.ABSTAINED:
            if reason_code == "identity_not_required":
                return IdentityContextState.NOT_REQUIRED
            if reason_code in {"low_confidence", "ambiguous_match"}:
                return IdentityContextState.LOW_CONFIDENCE
            if attribution.confidence_band in {ConfidenceBand.LOW, ConfidenceBand.AMBIGUOUS}:
                return IdentityContextState.LOW_CONFIDENCE
            return IdentityContextState.UNKNOWN

        return IdentityContextState.UNAVAILABLE


def _safe_id(value: str | None) -> str | None:
    return safe_token(value, "") or None
