from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.const import (
    DATA_ATTRIBUTION_CONTEXT_STORE,
    DATA_ATTRIBUTION_FOUNDATION,
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_GENERATE_VOICEPRINT_OPERATION,
    DATA_GENERATION_ORCHESTRATOR,
    DATA_GET_CAPABILITIES_OPERATION,
    DATA_GET_VOICEPRINT_STATUS_OPERATION,
    DATA_HEALTH_ENGINE,
    DATA_HEALTH_TELEMETRY_PROVIDER,
    DATA_IDENTITY_CONTEXT_GENERATOR,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_REPAIR_REGISTRY,
    DATA_REPAIR_RESOLVER,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DATA_VOICEPRINT_REVISION_MANAGER,
    DOMAIN,
)
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver
from custom_components.voice_identity.health_telemetry import VoiceIdentityHealthTelemetryProvider
from custom_components.voice_identity.attribution_context_store import InMemoryAttributionContextStore
from custom_components.voice_identity.attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
    ConfidenceBand,
    IdentityConfidenceLevel,
)
from custom_components.voice_identity.attribution_service import (
    SpeakerAttributionFoundation,
    build_runtime_attribution_record,
    create_attribution_request,
)
from custom_components.voice_identity.identity_context import IdentityContextGenerator
from custom_components.voice_identity.diagnostics import async_get_config_entry_diagnostics
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState
from custom_components.voice_identity.services import (
    SERVICE_ATTRIBUTE_SPEAKER,
    SERVICE_GET_DIAGNOSTICS,
    SERVICE_GET_HEALTH,
    SERVICE_GET_IDENTITY_CONTEXT,
    SERVICE_GET_REPAIRS,
    SERVICE_GET_TELEMETRY,
    async_register_services,
    async_unregister_services,
)


class _FakeServiceRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], object] = {}

    def async_register(self, domain, service, handler, schema=None, supports_response=None):
        _ = schema
        _ = supports_response
        self._handlers[(domain, service)] = handler

    def async_remove(self, domain, service):
        self._handlers.pop((domain, service), None)

    async def async_call(self, domain, service, data, *, return_response=False):
        handler = self._handlers[(domain, service)]
        call = SimpleNamespace(data=data)
        response = await handler(call)
        if return_response:
            return response
        return None


class _FakeHass:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}
        self.services = _FakeServiceRegistry()


def _runtime() -> dict[str, object]:
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
    )
    health = HealthSnapshot(
        state=HealthState.HEALTHY,
        reason_codes=("ready",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("model_provider_unavailable",),
                details={"provider": "backend_v1", "provider_available": False},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_registry_ready",),
                details={"loaded": True, "record_count": 0},
            ),
            ComponentHealthReport(
                component="generation_orchestrator",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("generation_orchestrator_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="generate_voiceprint_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("generate_voiceprint_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="get_voiceprint_status_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("get_voiceprint_status_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="get_capabilities_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("get_capabilities_ready",),
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
        ),
    )
    diagnostics_descriptor = SimpleNamespace(name="diagnostics")
    capability_registry = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            registry_schema_version=1,
            config_schema_version=1,
            capabilities=(SimpleNamespace(descriptor=diagnostics_descriptor, enabled=True),),
        )
    )

    repair_registry = VoiceIdentityRepairRegistry.with_defaults()
    repair_resolver = VoiceIdentityRepairResolver(registry=repair_registry)
    health_telemetry_provider = VoiceIdentityHealthTelemetryProvider()
    attribution_foundation = SpeakerAttributionFoundation()
    attribution_context_store = InMemoryAttributionContextStore()
    identity_context_generator = IdentityContextGenerator()

    return {
        DATA_CONFIG_MANAGER: SimpleNamespace(config=config),
        DATA_HEALTH_ENGINE: SimpleNamespace(snapshot=lambda: health),
        DATA_CAPABILITY_REGISTRY: capability_registry,
        DATA_MODEL_EXECUTION_PROVIDER: object(),
        DATA_VOICEPRINT_REGISTRY: object(),
        DATA_VOICEPRINT_LIFECYCLE_MANAGER: object(),
        DATA_VOICEPRINT_REVISION_MANAGER: object(),
        DATA_GENERATION_ORCHESTRATOR: object(),
        DATA_GENERATE_VOICEPRINT_OPERATION: object(),
        DATA_GET_VOICEPRINT_STATUS_OPERATION: object(),
        DATA_GET_CAPABILITIES_OPERATION: object(),
        DATA_HEALTH_TELEMETRY_PROVIDER: health_telemetry_provider,
        DATA_ATTRIBUTION_FOUNDATION: attribution_foundation,
        DATA_ATTRIBUTION_CONTEXT_STORE: attribution_context_store,
        DATA_IDENTITY_CONTEXT_GENERATOR: identity_context_generator,
        DATA_REPAIR_REGISTRY: repair_registry,
        DATA_REPAIR_RESOLVER: repair_resolver,
    }


class _FailingAttributionFoundation:
    async def attribute(self, *args, **kwargs):
        _ = args
        _ = kwargs
        raise AssertionError("attribute should not be called when store resolution succeeds")


@pytest.mark.asyncio
async def test_get_diagnostics_service_returns_safe_payload() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_DIAGNOSTICS,
        {},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["entry_id"] == "entry_1"
    assert response["diagnostics"]["platform"]["runtime_loaded"] is True
    assert "runtime_presence" in response["diagnostics"]


@pytest.mark.asyncio
async def test_get_diagnostics_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_DIAGNOSTICS,
        {"entry_id": "missing_entry"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"


@pytest.mark.asyncio
async def test_get_repairs_service_returns_structured_recommendations() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_REPAIRS,
        {},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["entry_id"] == "entry_1"
    assert response["repairs"]["status"] == "repair_available"
    assert response["repairs"]["repairable"] is True
    assert isinstance(response["repairs"]["repairs"], list)


@pytest.mark.asyncio
async def test_get_repairs_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_REPAIRS,
        {"entry_id": "missing_entry"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"
    assert response["repairs"]["status"] == "diagnostics_unavailable"


@pytest.mark.asyncio
async def test_get_health_service_returns_structured_health() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["entry_id"] == "entry_1"
    assert response["health"]["diagnostic_available"] is True
    assert response["health"]["repair_available"] is True
    assert response["health"]["readiness"]["attribution_readiness"] in {
        "ready",
        "degraded",
        "unavailable",
    }
    assert response["health"]["readiness"]["compatibility_readiness"] in {
        "ready",
        "degraded",
        "unavailable",
    }


@pytest.mark.asyncio
async def test_get_health_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {"entry_id": "missing_entry"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"
    assert response["health"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_get_telemetry_service_returns_privacy_safe_projection() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["telemetry"]["status"] == "telemetry_ready"
    assert response["telemetry"]["compatibility_readiness"] in {"ready", "degraded", "unavailable"}
    assert response["telemetry"]["attribution_readiness"] in {"ready", "degraded", "unavailable"}


@pytest.mark.asyncio
async def test_get_telemetry_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {"entry_id": "missing_entry"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"
    assert response["telemetry"]["status"] == "telemetry_unavailable"


@pytest.mark.asyncio
async def test_attribute_speaker_service_returns_advisory_projection() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ATTRIBUTE_SPEAKER,
        {"audio_ref": "sample_audio_001"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["attribution"]["status"] in {
        "attribution_ready",
        "attribution_abstained",
        "attribution_unavailable",
    }
    assert response["correlation"] == {
        "conversation_id": None,
        "device_id": None,
        "satellite_id": None,
        "room_id": None,
        "turn_index": None,
        "pipeline_id": None,
    }
    assert "diagnostic_summary" in response["attribution"]


@pytest.mark.asyncio
async def test_attribute_speaker_service_propagates_correlation_fields() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ATTRIBUTE_SPEAKER,
        {
            "audio_ref": "sample_audio_001",
            "conversation_id": "conv_1",
            "device_id": "device_kitchen",
            "satellite_id": "satellite_kitchen",
            "room_id": "kitchen",
            "turn_index": 7,
            "pipeline_id": "assist_pipeline_primary",
        },
        return_response=True,
    )

    assert response["correlation"] == {
        "conversation_id": "conv_1",
        "device_id": "device_kitchen",
        "satellite_id": "satellite_kitchen",
        "room_id": "kitchen",
        "turn_index": 7,
        "pipeline_id": "assist_pipeline_primary",
    }
    runtime = hass.data[DOMAIN]["entry_1"]
    store = runtime[DATA_ATTRIBUTION_CONTEXT_STORE]
    assert isinstance(store, InMemoryAttributionContextStore)
    assert response["runtime_attribution"]["state"] in {"unknown", "unavailable", "known", "ambiguous", "not_required"}
    if response["runtime_attribution"]["state"] in {"unknown", "unavailable"}:
        assert len(store._records) == 0
    else:
        assert len(store._records) == 1


@pytest.mark.asyncio
async def test_get_identity_context_prefers_store_resolution_over_re_attribution() -> None:
    hass = _FakeHass()
    runtime = _runtime()
    store = runtime[DATA_ATTRIBUTION_CONTEXT_STORE]
    assert isinstance(store, InMemoryAttributionContextStore)

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
    attribution = AttributionResult(
        success=True,
        status=AttributionStatus.READY,
        identity_confidence_level=IdentityConfidenceLevel.RECOGNIZED,
        attributed_person_id="person_123",
        attributed_profile_id="vp_123",
        attributed_artifact_id="artifact_123",
        confidence=0.92,
        confidence_band=ConfidenceBand.HIGH,
        reason_code="identity_known_high_confidence",
        attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
        is_confident=True,
        is_ambiguous=False,
        is_abstained=False,
        diagnostic_summary=AttributionDiagnosticSummary(
            diagnostic_available=True,
            diagnostic_reason_code="diagnostics_ready",
            repair_available=False,
            health_status="healthy",
            attribution_readiness="ready",
            compatibility_readiness="ready",
        ),
        repair_hint_code="review_component_health",
        suggested_next_action_code="no_action_required",
        health_status="healthy",
        readiness_status="ready",
    )
    store.upsert(
        build_runtime_attribution_record(
            request=request,
            attribution=attribution,
            now=datetime.now(timezone.utc),
        )
    )

    runtime[DATA_ATTRIBUTION_FOUNDATION] = _FailingAttributionFoundation()
    hass.data[DOMAIN] = {"entry_1": runtime}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {
            "conversation_id": "conv_1",
            "device_id": "device_kitchen",
            "satellite_id": "satellite_kitchen",
            "room_id": "kitchen",
            "turn_index": 1,
            "pipeline_id": "assist_pipeline_primary",
        },
        return_response=True,
    )

    assert response["success"] is True
    assert response["identity_context"]["state"] == "known"
    assert response["identity_context"]["person_id"] == "person_123"
    assert response["runtime_attribution"]["correlation"]["conversation_id"] == "conv_1"


@pytest.mark.asyncio
async def test_attribute_speaker_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ATTRIBUTE_SPEAKER,
        {"entry_id": "missing_entry", "audio_ref": "sample_audio_001"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"
    assert response["attribution"]["status"] == "attribution_unavailable"


@pytest.mark.asyncio
async def test_get_identity_context_service_returns_safe_projection() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {"audio_ref": "sample_audio_001"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["reason_code"] == "ready"
    assert response["correlation"] == {
        "conversation_id": None,
        "device_id": None,
        "satellite_id": None,
        "room_id": None,
        "turn_index": None,
        "pipeline_id": None,
    }
    assert response["identity_context"]["state"] in {
        "known",
        "unknown",
        "low_confidence",
        "unavailable",
    }
    assert response["identity_context"]["source"] == "voice_identity"


@pytest.mark.asyncio
async def test_get_identity_context_service_propagates_correlation_fields() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {
            "audio_ref": "sample_audio_001",
            "conversation_id": "conv_1",
            "device_id": "device_kitchen",
            "satellite_id": "satellite_kitchen",
            "room_id": "kitchen",
            "turn_index": 8,
            "pipeline_id": "assist_pipeline_primary",
        },
        return_response=True,
    )

    assert response["correlation"] == {
        "conversation_id": "conv_1",
        "device_id": "device_kitchen",
        "satellite_id": "satellite_kitchen",
        "room_id": "kitchen",
        "turn_index": 8,
        "pipeline_id": "assist_pipeline_primary",
    }


@pytest.mark.asyncio
async def test_get_identity_context_service_fails_closed_without_runtime() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    await async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {"entry_id": "missing_entry", "audio_ref": "sample_audio_001"},
        return_response=True,
    )

    assert response["success"] is False
    assert response["reason_code"] == "runtime_unavailable"
    assert response["identity_context"]["state"] == "unavailable"


@pytest.mark.asyncio
async def test_get_config_entry_diagnostics_uses_provider_payload() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}
    entry = SimpleNamespace(entry_id="entry_1")

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_id"] == "entry_1"
    assert diagnostics["source"] == "config_entry_diagnostics"
    assert diagnostics["platform"]["runtime_loaded"] is True
    assert "runtime_presence" in diagnostics


@pytest.mark.asyncio
async def test_unregister_removes_service() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry_1": _runtime()}

    await async_register_services(hass)
    await async_unregister_services(hass)

    assert (DOMAIN, SERVICE_GET_DIAGNOSTICS) not in hass.services._handlers
    assert (DOMAIN, SERVICE_GET_REPAIRS) not in hass.services._handlers
    assert (DOMAIN, SERVICE_GET_HEALTH) not in hass.services._handlers
    assert (DOMAIN, SERVICE_GET_TELEMETRY) not in hass.services._handlers
    assert (DOMAIN, SERVICE_ATTRIBUTE_SPEAKER) not in hass.services._handlers
    assert (DOMAIN, SERVICE_GET_IDENTITY_CONTEXT) not in hass.services._handlers
