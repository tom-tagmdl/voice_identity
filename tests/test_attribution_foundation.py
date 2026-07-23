from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.attribution_models import ConfidenceBand, IdentityConfidenceLevel
from custom_components.voice_identity.attribution_service import (
    SpeakerAttributionFoundation,
    build_runtime_attribution_record,
    create_attribution_request,
)
from custom_components.voice_identity.attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
)
from custom_components.voice_identity.health_telemetry import VoiceIdentityHealthTelemetryProvider
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver


class _Registry:
    def __init__(self, records: list[object]) -> None:
        self._records = records

    def list_active_records(self):
        return tuple(self._records)


def _record(voiceprint_id: str, artifact_id: str, subject_id: str) -> object:
    return SimpleNamespace(
        voiceprint_id=SimpleNamespace(value=voiceprint_id),
        artifact_id=SimpleNamespace(value=artifact_id),
        subject_id=SimpleNamespace(value=subject_id),
    )


def _runtime(
    *,
    attribution_readiness: str = "ready",
    records: list[object] | None = None,
    include_model_provider: bool = True,
) -> dict[str, object]:
    readiness_health = HealthState.HEALTHY if attribution_readiness == "ready" else HealthState.UNAVAILABLE
    health = HealthSnapshot(
        state=readiness_health,
        reason_codes=("health_ready",) if readiness_health is HealthState.HEALTHY else ("health_unavailable",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=HealthState.HEALTHY if include_model_provider else HealthState.UNAVAILABLE,
                reason_codes=("model_execution_ready",)
                if include_model_provider
                else ("model_provider_unavailable",),
                details={"provider_available": include_model_provider},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_registry_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="voiceprint_lifecycle_manager",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_lifecycle_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="voiceprint_revision_manager",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_revision_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="storage_provider",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("storage_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="get_capabilities_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("capability_discovery_ready",),
                details={"loaded": True},
            ),
        ),
    )

    config = SimpleNamespace(
        config_schema_version=1,
        service=SimpleNamespace(enabled=True),
        diagnostics=SimpleNamespace(enabled=True),
        generation=SimpleNamespace(
            model_preference="ecapa_v1",
            supported_models=("ecapa_v1",),
            min_sample_count=8,
            max_sample_count=12,
            quality_threshold=0.75,
        ),
        attribution=SimpleNamespace(default_confidence_threshold=0.7),
    )

    runtime = {
        "config_manager": SimpleNamespace(config=config),
        "health_engine": SimpleNamespace(snapshot=lambda: health),
        "health_telemetry_provider": _AsyncHealthProvider(attribution_readiness=attribution_readiness),
        "repair_resolver": VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()),
        "voiceprint_registry": _Registry(records or []),
    }
    if include_model_provider:
        runtime["model_execution_provider"] = object()
    return runtime


class _AsyncHealthProvider(VoiceIdentityHealthTelemetryProvider):
    def __init__(self, *, attribution_readiness: str) -> None:
        super().__init__()
        self._attribution_readiness = attribution_readiness

    async def collect_health(self, *, context, services_registered: bool):
        _ = context
        _ = services_registered
        return _health_payload(attribution_readiness=self._attribution_readiness)


def _health_payload(*, attribution_readiness: str) -> dict[str, object]:
    return {
        "status": "healthy" if attribution_readiness == "ready" else "unavailable",
        "diagnostics_status": {"available": True, "reason_code": "diagnostics_ready"},
        "readiness": {
            "attribution_readiness": attribution_readiness,
            "compatibility_readiness": "ready" if attribution_readiness == "ready" else "unavailable",
        },
    }


def _diagnostic_summary() -> AttributionDiagnosticSummary:
    return AttributionDiagnosticSummary(
        diagnostic_available=True,
        diagnostic_reason_code="diagnostics_ready",
        repair_available=False,
        health_status="healthy",
        attribution_readiness="ready",
        compatibility_readiness="ready",
    )


def _attribution_result(
    *,
    status: AttributionStatus,
    reason_code: str,
    confidence_band: ConfidenceBand,
    confidence: float,
    person_id: str | None,
    profile_id: str | None,
) -> AttributionResult:
    return AttributionResult(
        success=True,
        status=status,
        identity_confidence_level=(
            IdentityConfidenceLevel.RECOGNIZED
            if status is AttributionStatus.READY and person_id is not None
            else IdentityConfidenceLevel.UNKNOWN
        ),
        attributed_person_id=person_id,
        attributed_profile_id=profile_id,
        attributed_artifact_id=None,
        confidence=confidence,
        confidence_band=confidence_band,
        reason_code=reason_code,
        attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
        is_confident=status is AttributionStatus.READY,
        is_ambiguous=reason_code == "ambiguous_match",
        is_abstained=status is not AttributionStatus.READY,
        diagnostic_summary=_diagnostic_summary(),
        repair_hint_code="review_component_health",
        suggested_next_action_code="no_action_required",
        health_status="healthy",
        readiness_status="ready",
    )


@pytest.mark.asyncio
async def test_attribution_returns_unavailable_when_not_ready() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(attribution_readiness="unavailable")
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.status.value == "attribution_unavailable"
    assert result.reason_code == "attribution_not_ready"
    assert result.is_abstained is True


@pytest.mark.asyncio
async def test_attribution_returns_unknown_when_no_audio_evidence() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(attribution_readiness="ready")
    request = create_attribution_request({})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.identity_confidence_level is IdentityConfidenceLevel.UNKNOWN
    assert result.reason_code == "identity_unknown"


@pytest.mark.asyncio
async def test_attribution_returns_no_active_voiceprints() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(attribution_readiness="ready", records=[])
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.reason_code == "no_active_voiceprints"
    assert result.confidence_band is ConfidenceBand.NO_MATCH


@pytest.mark.asyncio
async def test_attribution_returns_ambiguous_for_multiple_candidates() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(
        attribution_readiness="ready",
        records=[_record("vp_001", "artifact_001", "person_1"), _record("vp_002", "artifact_002", "person_2")],
    )
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.reason_code == "ambiguous_match"
    assert result.is_ambiguous is True


@pytest.mark.asyncio
async def test_attribution_returns_recognized_for_single_candidate() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(
        attribution_readiness="ready",
        records=[_record("vp_001", "artifact_001", "person_1")],
    )
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.status.value == "attribution_ready"
    assert result.identity_confidence_level is IdentityConfidenceLevel.RECOGNIZED
    assert result.attributed_person_id == "person_1"
    assert result.attributed_profile_id == "vp_001"


@pytest.mark.asyncio
async def test_attribution_is_deterministic_for_identical_input() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(
        attribution_readiness="ready",
        records=[_record("vp_001", "artifact_001", "person_1")],
    )
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    first = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )
    second = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert first.to_dict() == second.to_dict()


@pytest.mark.asyncio
async def test_attribution_fails_closed_when_model_provider_missing() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(
        attribution_readiness="ready",
        records=[_record("vp_001", "artifact_001", "person_1")],
        include_model_provider=False,
    )
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    assert result.reason_code == "model_backend_unavailable"


def test_attribution_request_validation_sanitizes_scope() -> None:
    request = create_attribution_request(
        {
            "audio_ref": "Session_Audio_001",
            "candidate_scope": ["person_1", "PERSON_1", "person_2"],
            "model_preference": "ecapa_v1",
        }
    )

    assert request.audio_ref == "session_audio_001"
    assert request.candidate_scope == ("person_1", "person_2")
    assert request.conversation_id is None
    assert request.device_id is None
    assert request.satellite_id is None
    assert request.room_id is None
    assert request.turn_index is None
    assert request.pipeline_id is None


def test_attribution_request_parses_correlation_fields_null_safely() -> None:
    request = create_attribution_request(
        {
            "audio_ref": "sample_audio_001",
            "conversation_id": "conv_1",
            "device_id": "device_kitchen",
            "satellite_id": "satellite_kitchen",
            "room_id": "kitchen",
            "turn_index": "4",
            "pipeline_id": "assist_pipeline_primary",
        }
    )

    assert request.conversation_id == "conv_1"
    assert request.device_id == "device_kitchen"
    assert request.satellite_id == "satellite_kitchen"
    assert request.room_id == "kitchen"
    assert request.turn_index == 4
    assert request.pipeline_id == "assist_pipeline_primary"
    assert request.correlation_payload() == {
        "conversation_id": "conv_1",
        "device_id": "device_kitchen",
        "satellite_id": "satellite_kitchen",
        "room_id": "kitchen",
        "turn_index": 4,
        "pipeline_id": "assist_pipeline_primary",
    }


def test_attribution_request_invalid_turn_index_falls_back_to_none() -> None:
    request = create_attribution_request(
        {
            "audio_ref": "sample_audio_001",
            "turn_index": "not-an-int",
        }
    )

    assert request.turn_index is None


@pytest.mark.parametrize(
    ("status", "reason_code", "band", "expected_state", "expected_ttl"),
    [
        (AttributionStatus.READY, "attribution_ready", ConfidenceBand.HIGH, "known", 30),
        (AttributionStatus.ABSTAINED, "ambiguous_match", ConfidenceBand.AMBIGUOUS, "ambiguous", 5),
        (AttributionStatus.ABSTAINED, "identity_unknown", ConfidenceBand.UNKNOWN, "unknown", 0),
        (AttributionStatus.UNAVAILABLE, "attribution_unavailable", ConfidenceBand.UNAVAILABLE, "unavailable", 0),
        (AttributionStatus.ABSTAINED, "identity_not_required", ConfidenceBand.UNKNOWN, "not_required", 10),
    ],
)
def test_runtime_record_builder_covers_required_states_and_ttl(
    status: AttributionStatus,
    reason_code: str,
    band: ConfidenceBand,
    expected_state: str,
    expected_ttl: int,
) -> None:
    request = create_attribution_request(
        {
            "conversation_id": "conv_1",
            "device_id": "device_kitchen",
            "satellite_id": "satellite_kitchen",
            "room_id": "kitchen",
            "turn_index": 1,
            "pipeline_id": "assist_pipeline_primary",
        }
    )
    attribution = _attribution_result(
        status=status,
        reason_code=reason_code,
        confidence_band=band,
        confidence=0.92 if expected_state == "known" else 0.0,
        person_id="person_1" if expected_state == "known" else None,
        profile_id="vp_1" if expected_state == "known" else None,
    )

    record = build_runtime_attribution_record(request=request, attribution=attribution)

    issued = datetime.fromisoformat(record.issued_at_utc)
    expires = datetime.fromisoformat(record.expires_at_utc)
    ttl_seconds = int((expires - issued).total_seconds())

    assert record.decision.state == expected_state
    assert ttl_seconds == expected_ttl
    assert record.binding.conversation_id == "conv_1"
    assert record.binding.device_id == "device_kitchen"
    assert record.binding.satellite_id == "satellite_kitchen"
    assert record.binding.room_id == "kitchen"
    assert record.binding.turn_index == 1
    assert record.binding.pipeline_id == "assist_pipeline_primary"


@pytest.mark.asyncio
async def test_attribution_result_serialization_is_privacy_safe() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime(
        attribution_readiness="ready",
        records=[_record("vp_001", "artifact_001", "person_1")],
    )
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime,
        request=request,
        services_registered=True,
    )

    payload = result.to_dict()
    serialized = str(payload).lower()
    for forbidden in {
        "audio_bytes",
        "embedding",
        "vector",
        "transcript",
        "path",
        "traceback",
    }:
        assert forbidden not in serialized
