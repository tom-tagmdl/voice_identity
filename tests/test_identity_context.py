from __future__ import annotations

from custom_components.voice_identity.attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
    ConfidenceBand,
    IdentityConfidenceLevel,
)
from custom_components.voice_identity.identity_context import IdentityContextGenerator


def _summary() -> AttributionDiagnosticSummary:
    return AttributionDiagnosticSummary(
        diagnostic_available=True,
        diagnostic_reason_code="diagnostics_ready",
        repair_available=True,
        health_status="healthy",
        attribution_readiness="ready",
        compatibility_readiness="ready",
    )


def _result(
    *,
    status: AttributionStatus,
    identity_confidence_level: IdentityConfidenceLevel,
    reason_code: str,
    confidence_band: ConfidenceBand,
    confidence: float = 0.0,
    attributed_person_id: str | None = None,
    attributed_profile_id: str | None = None,
) -> AttributionResult:
    return AttributionResult(
        success=True,
        status=status,
        identity_confidence_level=identity_confidence_level,
        attributed_person_id=attributed_person_id,
        attributed_profile_id=attributed_profile_id,
        attributed_artifact_id=None,
        confidence=confidence,
        confidence_band=confidence_band,
        reason_code=reason_code,
        attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
        is_confident=False,
        is_ambiguous=False,
        is_abstained=status is not AttributionStatus.READY,
        diagnostic_summary=_summary(),
        repair_hint_code="review_component_health",
        suggested_next_action_code="review_component_health",
        health_status="healthy",
        readiness_status="ready",
    )


def test_identity_context_maps_known() -> None:
    generator = IdentityContextGenerator()
    attribution = _result(
        status=AttributionStatus.READY,
        identity_confidence_level=IdentityConfidenceLevel.RECOGNIZED,
        reason_code="attribution_ready",
        confidence_band=ConfidenceBand.HIGH,
        confidence=0.92,
        attributed_person_id="person_1",
        attributed_profile_id="vp_1",
    )

    context = generator.generate(attribution=attribution)
    payload = generator.to_dict(context=context)

    assert payload["state"] == "known"
    assert payload["person_id"] == "person_1"
    assert payload["voice_profile_id"] == "vp_1"
    assert payload["confidence"] == 0.92
    assert payload["confidence_band"] == "high"
    assert payload["source"] == "voice_identity"


def test_identity_context_maps_unknown() -> None:
    generator = IdentityContextGenerator()
    attribution = _result(
        status=AttributionStatus.ABSTAINED,
        identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
        reason_code="identity_unknown",
        confidence_band=ConfidenceBand.UNKNOWN,
    )

    payload = generator.to_dict(context=generator.generate(attribution=attribution))

    assert payload["state"] == "unknown"
    assert payload["person_id"] is None
    assert payload["voice_profile_id"] is None
    assert payload["confidence"] is None
    assert payload["confidence_band"] is None


def test_identity_context_maps_low_confidence() -> None:
    generator = IdentityContextGenerator()
    attribution = _result(
        status=AttributionStatus.ABSTAINED,
        identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
        reason_code="low_confidence",
        confidence_band=ConfidenceBand.LOW,
        confidence=0.61,
    )

    payload = generator.to_dict(context=generator.generate(attribution=attribution))

    assert payload["state"] == "low_confidence"
    assert payload["confidence"] == 0.61
    assert payload["confidence_band"] == "low"
    assert payload["person_id"] is None
    assert payload["voice_profile_id"] is None


def test_identity_context_maps_unavailable() -> None:
    generator = IdentityContextGenerator()
    attribution = _result(
        status=AttributionStatus.UNAVAILABLE,
        identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
        reason_code="attribution_unavailable",
        confidence_band=ConfidenceBand.UNAVAILABLE,
    )

    payload = generator.to_dict(context=generator.generate(attribution=attribution))

    assert payload["state"] == "unavailable"
    assert payload["reason_code"] == "attribution_unavailable"
