from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.attribution_models import AttributionStatus
from custom_components.voice_identity.attribution_service import SpeakerAttributionFoundation, create_attribution_request
from custom_components.voice_identity.capability_discovery_operation import GetCapabilitiesOperation, GetCapabilitiesRequest
from custom_components.voice_identity.capability_discovery_operation import (
    CompatibilityDiscoveryRequest,
    CompatibilityStatus,
)
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import (
    VoiceIdentityConfigMigrationRequiredError,
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigurationValidationError,
)
from custom_components.voice_identity.const import (
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
    DATA_REPAIR_RESOLVER,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DATA_VOICEPRINT_REVISION_MANAGER,
    DOMAIN,
)
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState
from custom_components.voice_identity.health_telemetry import (
    VoiceIdentityHealthTelemetryProvider,
    build_health_telemetry_context,
)
from custom_components.voice_identity.identity_context import IdentityContextGenerator
from custom_components.voice_identity.model_execution import (
    BackendExecutionRequest,
    BackendExecutionResult,
    ModelBackendExecutionError,
    ModelExecutionProviderRuntime,
    ModelProviderMetadata,
    UnavailableModelExecutionBackend,
)
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver
from custom_components.voice_identity.services import (
    SERVICE_GET_IDENTITY_CONTEXT,
    SERVICE_GET_TELEMETRY,
    async_register_services,
)


class _Entry:
    entry_id = "entry"

    def __init__(self, *, data: dict[str, object] | None = None) -> None:
        self.data = data or {}
        self.options: dict[str, object] = {}


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


class _CapabilityRegistry:
    def __init__(self, *, available: bool = True) -> None:
        self._available = available

    def snapshot(self):
        if not self._available:
            raise RuntimeError("capability registry unavailable")
        diagnostics_descriptor = SimpleNamespace(name="diagnostics", maturity="implemented")
        return SimpleNamespace(
            registry_schema_version=1,
            config_schema_version=1,
            capabilities=(SimpleNamespace(descriptor=diagnostics_descriptor, enabled=True),),
        )


class _Registry:
    def __init__(self, records: list[object]) -> None:
        self._records = records

    def list_active_records(self):
        return tuple(self._records)


class _RaisingRegistry:
    def list_active_records(self):
        raise RuntimeError("C:/sensitive/registry-failure")


class _RaisingDiagnosticsProvider:
    async def collect(self, *, context, source):
        _ = context
        _ = source
        raise RuntimeError("token=abc123")


class _RaisingTelemetryProvider(VoiceIdentityHealthTelemetryProvider):
    async def collect_telemetry(self, *, context, services_registered):
        _ = context
        _ = services_registered
        raise RuntimeError("traceback: /private/path")


class _RaisingIdentityContextGenerator(IdentityContextGenerator):
    def generate(self, *, attribution):  # type: ignore[override]
        _ = attribution
        raise RuntimeError("secret/path")


class _ReadyBackend:
    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        raise_reason: str | None = None,
        raise_internal: bool = False,
        provider_available: bool = True,
    ) -> None:
        self._delay_seconds = delay_seconds
        self._raise_reason = raise_reason
        self._raise_internal = raise_internal
        self._provider_available = provider_available

    @property
    def metadata(self) -> ModelProviderMetadata:
        return ModelProviderMetadata(
            provider_name="test_backend",
            provider_version="1",
            supported_models=("ecapa_v1",),
            supported_representation_formats=("encrypted_representation_v1",),
            available=self._provider_available,
        )

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        _ = request
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._raise_reason is not None:
            raise ModelBackendExecutionError(self._raise_reason)
        if self._raise_internal:
            raise RuntimeError("C:/private/exception")
        return BackendExecutionResult(
            encrypted_payload=b"enc_payload_v1",
            payload_format_version=1,
            encryption_scheme="aes_gcm_v1",
            key_reference="key_ref_v1",
            model_version="v1",
            schema_version=1,
            representation_format="encrypted_representation_v1",
            provider_confidence=0.9,
        )


@dataclass
class _ScenarioRuntime:
    runtime: dict[str, object]
    snapshot: HealthSnapshot


def _record(voiceprint_id: str, artifact_id: str, subject_id: str) -> object:
    return SimpleNamespace(
        voiceprint_id=SimpleNamespace(value=voiceprint_id),
        artifact_id=SimpleNamespace(value=artifact_id),
        subject_id=SimpleNamespace(value=subject_id),
    )


def _health_snapshot(
    *,
    model_state: HealthState = HealthState.HEALTHY,
    registry_state: HealthState = HealthState.HEALTHY,
    storage_state: HealthState = HealthState.HEALTHY,
    capability_state: HealthState = HealthState.HEALTHY,
    migration_required: bool = False,
) -> HealthSnapshot:
    if migration_required:
        state = HealthState.MIGRATION_REQUIRED
        reason_codes = ("configuration_migration_required",)
    elif HealthState.UNAVAILABLE in {model_state, registry_state, storage_state, capability_state}:
        state = HealthState.UNAVAILABLE
        reason_codes = ("dependency_unavailable",)
    elif HealthState.DEGRADED in {model_state, registry_state, storage_state, capability_state}:
        state = HealthState.DEGRADED
        reason_codes = ("dependency_degraded",)
    else:
        state = HealthState.HEALTHY
        reason_codes = ("health_ready",)

    return HealthSnapshot(
        state=state,
        reason_codes=reason_codes,
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=model_state,
                reason_codes=("model_provider_ready",)
                if model_state is HealthState.HEALTHY
                else ("model_provider_unavailable",),
                details={"provider_available": model_state is HealthState.HEALTHY},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=registry_state,
                reason_codes=("voiceprint_registry_ready",)
                if registry_state is HealthState.HEALTHY
                else ("voiceprint_artifact_missing",),
                details={"loaded": registry_state is HealthState.HEALTHY, "record_count": 1},
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
                state=storage_state,
                reason_codes=("storage_provider_ready",)
                if storage_state is HealthState.HEALTHY
                else ("storage_provider_unavailable",),
                details={"loaded": storage_state is HealthState.HEALTHY},
            ),
            ComponentHealthReport(
                component="get_capabilities_operation",
                required=True,
                state=capability_state,
                reason_codes=("get_capabilities_ready",)
                if capability_state is HealthState.HEALTHY
                else ("operation_not_loaded",),
                details={"loaded": capability_state is HealthState.HEALTHY},
            ),
        ),
    )


def _runtime_fixture(
    *,
    records: list[object] | None = None,
    registry_obj: object | None = None,
    snapshot: HealthSnapshot | None = None,
    include_model_provider: bool = True,
    include_repair_resolver: bool = True,
    capability_available: bool = True,
    health_provider: object | None = None,
    identity_context_generator: object | None = None,
) -> _ScenarioRuntime:
    selected_snapshot = snapshot or _health_snapshot()
    config = SimpleNamespace(
        config_schema_version=1,
        service=SimpleNamespace(enabled=True),
        diagnostics=SimpleNamespace(enabled=True),
        generation=SimpleNamespace(
            model_preference="ecapa_v1",
            supported_models=("ecapa_v1",),
            min_sample_count=6,
            max_sample_count=12,
            quality_threshold=0.75,
        ),
        attribution=SimpleNamespace(default_confidence_threshold=0.7),
    )
    runtime: dict[str, object] = {
        DATA_CONFIG_MANAGER: SimpleNamespace(config=config),
        DATA_HEALTH_ENGINE: SimpleNamespace(snapshot=lambda: selected_snapshot),
        DATA_CAPABILITY_REGISTRY: _CapabilityRegistry(available=capability_available),
        DATA_VOICEPRINT_REGISTRY: registry_obj if registry_obj is not None else _Registry(records or []),
        DATA_VOICEPRINT_LIFECYCLE_MANAGER: object(),
        DATA_VOICEPRINT_REVISION_MANAGER: object(),
        DATA_GENERATION_ORCHESTRATOR: object(),
        DATA_GENERATE_VOICEPRINT_OPERATION: object(),
        DATA_GET_VOICEPRINT_STATUS_OPERATION: object(),
        DATA_GET_CAPABILITIES_OPERATION: object(),
        DATA_HEALTH_TELEMETRY_PROVIDER: health_provider
        if health_provider is not None
        else VoiceIdentityHealthTelemetryProvider(),
        DATA_ATTRIBUTION_FOUNDATION: SpeakerAttributionFoundation(),
        DATA_IDENTITY_CONTEXT_GENERATOR: identity_context_generator
        if identity_context_generator is not None
        else IdentityContextGenerator(),
    }
    if include_model_provider:
        runtime[DATA_MODEL_EXECUTION_PROVIDER] = object()
    if include_repair_resolver:
        runtime[DATA_REPAIR_RESOLVER] = VoiceIdentityRepairResolver(
            registry=VoiceIdentityRepairRegistry.with_defaults()
        )
    return _ScenarioRuntime(runtime=runtime, snapshot=selected_snapshot)


def _forbidden_leaks(value: object) -> None:
    rendered = str(value).lower()
    for forbidden in {
        "raw_audio",
        "enrollment_audio",
        "transcript",
        "embedding",
        "vector",
        "fingerprint",
        "payload",
        "secret",
        "token",
        "traceback",
        "c:/",
        "/private/",
    }:
        assert forbidden not in rendered


def _model_config_manager(*, schema_version: object | None = None) -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    data: dict[str, object] = {
        "generation": {
            "model_preference": "ecapa_v1",
            "min_sample_count": 2,
            "max_sample_count": 12,
            "quality_threshold": 0.75,
            "supported_models": ["ecapa_v1"],
        }
    }
    if schema_version is not None:
        data["config_schema_version"] = schema_version
    manager.load_from_entry(_Entry(data=data))
    return manager


@pytest.mark.asyncio
async def test_fault_runtime_unavailable_and_missing_entry_with_recovery() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}
    await async_register_services(hass)

    missing = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {"entry_id": "missing_entry"},
        return_response=True,
    )
    assert missing["success"] is False
    assert missing["reason_code"] == "runtime_unavailable"

    healthy = _runtime_fixture(records=[_record("vp_001", "artifact_001", "person_1")])
    hass.data[DOMAIN]["entry_1"] = healthy.runtime
    recovered = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {},
        return_response=True,
    )
    assert recovered["success"] is True
    assert recovered["telemetry"]["status"] in {"telemetry_ready", "telemetry_degraded"}
    _forbidden_leaks(recovered)


@pytest.mark.asyncio
async def test_fault_registry_unavailable_empty_malformed_and_recovery() -> None:
    foundation = SpeakerAttributionFoundation()
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    healthy = _runtime_fixture(records=[_record("vp_001", "artifact_001", "person_1")])
    baseline = await foundation.attribute(
        entry_id="entry_1",
        runtime=healthy.runtime,
        request=request,
        services_registered=True,
    )
    assert baseline.reason_code != "registry_unavailable"

    unavailable_runtime = _runtime_fixture(registry_obj=object())
    unavailable = await foundation.attribute(
        entry_id="entry_1",
        runtime=unavailable_runtime.runtime,
        request=request,
        services_registered=True,
    )
    assert unavailable.reason_code == "registry_unavailable"

    empty_runtime = _runtime_fixture(records=[])
    empty = await foundation.attribute(
        entry_id="entry_1",
        runtime=empty_runtime.runtime,
        request=request,
        services_registered=True,
    )
    assert empty.reason_code == "no_active_voiceprints"

    malformed_runtime = _runtime_fixture(registry_obj=_RaisingRegistry())
    malformed = await foundation.attribute(
        entry_id="entry_1",
        runtime=malformed_runtime.runtime,
        request=request,
        services_registered=True,
    )
    assert malformed.reason_code == "internal_error"
    _forbidden_leaks(malformed.to_dict())

    recovered = await foundation.attribute(
        entry_id="entry_1",
        runtime=healthy.runtime,
        request=request,
        services_registered=True,
    )
    assert recovered.reason_code != "registry_unavailable"


@pytest.mark.asyncio
async def test_fault_missing_artifact_reference_fails_closed() -> None:
    foundation = SpeakerAttributionFoundation()
    runtime = _runtime_fixture(records=[_record("vp_001", "", "person_1")])
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    result = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime.runtime,
        request=request,
        services_registered=True,
    )

    assert result.reason_code == "no_active_voiceprints"
    assert result.status is AttributionStatus.ABSTAINED


@pytest.mark.asyncio
async def test_fault_model_backend_unavailable_timeout_exception_and_recovery() -> None:
    request = SimpleNamespace(
        identifiers=SimpleNamespace(generation_id="gen_001"),
        options=SimpleNamespace(model_preference="ecapa_v1", timeout_seconds=1.0),
        sample_references=("sample_1", "sample_2"),
        prepared_enrollment_inputs=("prepared_1",),
    )
    validation = SimpleNamespace(passed=True)
    quality = SimpleNamespace(passed=True)

    unavailable = ModelExecutionProviderRuntime.create(
        config_manager=_model_config_manager(),
        backend=UnavailableModelExecutionBackend(),
    )
    unavailable_result = await unavailable.generate(request=request, validation=validation, quality=quality)
    assert unavailable_result.reason_code == "model_provider_unavailable"

    timeout_provider = ModelExecutionProviderRuntime.create(
        config_manager=_model_config_manager(),
        backend=_ReadyBackend(delay_seconds=0.05),
    )
    timeout_request = SimpleNamespace(
        identifiers=SimpleNamespace(generation_id="gen_001"),
        options=SimpleNamespace(model_preference="ecapa_v1", timeout_seconds=0.001),
        sample_references=("sample_1", "sample_2"),
        prepared_enrollment_inputs=("prepared_1",),
    )
    timeout_result = await timeout_provider.generate(
        request=timeout_request,
        validation=validation,
        quality=quality,
    )
    assert timeout_result.reason_code == "model_timeout"

    exception_provider = ModelExecutionProviderRuntime.create(
        config_manager=_model_config_manager(),
        backend=_ReadyBackend(raise_internal=True),
    )
    exception_result = await exception_provider.generate(
        request=request,
        validation=validation,
        quality=quality,
    )
    assert exception_result.reason_code == "model_internal_error"
    _forbidden_leaks(str(exception_result))

    recovered_provider = ModelExecutionProviderRuntime.create(
        config_manager=_model_config_manager(),
        backend=_ReadyBackend(),
    )
    recovered_result = await recovered_provider.generate(
        request=request,
        validation=validation,
        quality=quality,
    )
    assert recovered_result.reason_code == "model_execution_ready"


@pytest.mark.asyncio
async def test_fault_invalid_configuration_and_version_metadata_paths() -> None:
    with pytest.raises(VoiceIdentityConfigMigrationRequiredError):
        _model_config_manager(schema_version=0)

    with pytest.raises(VoiceIdentityConfigurationValidationError):
        manager = VoiceIdentityConfigurationManager()
        manager.load_from_entry(_Entry(data={"config_schema_version": "malformed"}))

    manager = _model_config_manager()
    operation = GetCapabilitiesOperation.create(
        capability_registry=VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    )

    missing_version = await operation.execute(
        GetCapabilitiesRequest(requested_contract_version=1, requested_schema_version=None)  # type: ignore[arg-type]
    )
    assert missing_version.success is False
    assert missing_version.reason_code == "schema_version_unsupported"

    malformed_version = await operation.execute(
        GetCapabilitiesRequest(requested_contract_version=1, requested_schema_version="bad")  # type: ignore[arg-type]
    )
    assert malformed_version.success is False
    assert malformed_version.reason_code == "schema_version_unsupported"

    unsupported_schema = await operation.execute(
        GetCapabilitiesRequest(requested_contract_version=1, requested_schema_version=99)
    )
    assert unsupported_schema.success is False
    assert unsupported_schema.reason_code == "schema_version_unsupported"


@pytest.mark.asyncio
async def test_fault_diagnostics_and_repairs_observability_and_recovery() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()
    faulty_runtime = _runtime_fixture(include_repair_resolver=False)
    provider._diagnostics_provider = _RaisingDiagnosticsProvider()  # type: ignore[attr-defined]

    faulty = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=faulty_runtime.runtime),
        services_registered=True,
    )
    assert faulty["diagnostics_status"]["reason_code"] == "diagnostics_unavailable"
    assert faulty["repair_status"]["reason_code"] == "repair_framework_unavailable"

    recovered_runtime = _runtime_fixture()
    recovered_provider = VoiceIdentityHealthTelemetryProvider()
    recovered = await recovered_provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=recovered_runtime.runtime),
        services_registered=True,
    )
    assert recovered["diagnostics_status"]["reason_code"] == "diagnostics_ready"
    assert recovered["repair_status"]["available"] in {True, False}


@pytest.mark.asyncio
async def test_fault_health_and_telemetry_provider_unavailable_with_recovery() -> None:
    foundation = SpeakerAttributionFoundation()
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    no_health_runtime = _runtime_fixture()
    no_health_runtime.runtime.pop(DATA_HEALTH_TELEMETRY_PROVIDER, None)
    unavailable = await foundation.attribute(
        entry_id="entry_1",
        runtime=no_health_runtime.runtime,
        request=request,
        services_registered=True,
    )
    assert unavailable.reason_code == "attribution_not_ready"

    hass = _FakeHass()
    runtime = _runtime_fixture(health_provider=_RaisingTelemetryProvider())
    hass.data[DOMAIN] = {"entry_1": runtime.runtime}
    await async_register_services(hass)

    telemetry_unavailable = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {},
        return_response=True,
    )
    assert telemetry_unavailable["success"] is False
    assert telemetry_unavailable["reason_code"] == "telemetry_unavailable"
    _forbidden_leaks(telemetry_unavailable)

    recovered_runtime = _runtime_fixture()
    hass.data[DOMAIN]["entry_1"] = recovered_runtime.runtime
    telemetry_recovered = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {},
        return_response=True,
    )
    assert telemetry_recovered["success"] is True


@pytest.mark.asyncio
async def test_fault_identity_context_dependency_unavailable_and_recovery() -> None:
    hass = _FakeHass()
    faulty_runtime = _runtime_fixture(identity_context_generator=_RaisingIdentityContextGenerator())
    hass.data[DOMAIN] = {"entry_1": faulty_runtime.runtime}
    await async_register_services(hass)

    unavailable = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {"audio_ref": "sample_audio_001"},
        return_response=True,
    )
    assert unavailable["success"] is False
    assert unavailable["reason_code"] == "identity_context_unavailable"
    assert unavailable["identity_context"]["state"] == "unavailable"
    _forbidden_leaks(unavailable)

    recovered_runtime = _runtime_fixture()
    hass.data[DOMAIN]["entry_1"] = recovered_runtime.runtime
    recovered = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        {"audio_ref": "sample_audio_001"},
        return_response=True,
    )
    assert recovered["success"] is True
    assert recovered["identity_context"]["state"] in {
        "known",
        "unknown",
        "low_confidence",
        "unavailable",
    }


@pytest.mark.asyncio
async def test_fault_capability_and_compatibility_readiness_degradation_and_recovery() -> None:
    degraded_snapshot = _health_snapshot(
        model_state=HealthState.UNAVAILABLE,
        capability_state=HealthState.UNAVAILABLE,
        storage_state=HealthState.UNAVAILABLE,
    )
    degraded_runtime = _runtime_fixture(
        snapshot=degraded_snapshot,
        capability_available=False,
    )
    provider = VoiceIdentityHealthTelemetryProvider()

    degraded_health = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=degraded_runtime.runtime),
        services_registered=True,
    )
    degraded_telemetry = await provider.collect_telemetry(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=degraded_runtime.runtime),
        services_registered=True,
    )

    assert degraded_health["readiness"]["compatibility_readiness"] == "unavailable"
    assert degraded_telemetry["capability_status"]["reason_code"] == "capability_registry_unavailable"

    recovered_runtime = _runtime_fixture(snapshot=_health_snapshot())
    recovered_health = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=recovered_runtime.runtime),
        services_registered=True,
    )
    assert recovered_health["readiness"]["compatibility_readiness"] in {"ready", "degraded"}


@pytest.mark.asyncio
async def test_fault_migration_required_readiness_state() -> None:
    migration_runtime = _runtime_fixture(snapshot=_health_snapshot(migration_required=True))
    provider = VoiceIdentityHealthTelemetryProvider()

    health = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=migration_runtime.runtime),
        services_registered=True,
    )

    assert health["status"] == "migration_required"
    assert health["reason_code"] == "configuration_migration_required"
    assert health["readiness"]["attribution_readiness"] == "ready"


@pytest.mark.asyncio
async def test_fault_storage_provider_unavailable_is_observable() -> None:
    storage_fault = _runtime_fixture(
        snapshot=_health_snapshot(storage_state=HealthState.UNAVAILABLE)
    )
    provider = VoiceIdentityHealthTelemetryProvider()

    health = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=storage_fault.runtime),
        services_registered=True,
    )

    component_reason_codes = {
        item["reason_code"] for item in health["component_status"] if item["component"] == "storage_provider"
    }
    assert "storage_provider_unavailable" in component_reason_codes


@pytest.mark.asyncio
async def test_fault_no_unsafe_success_on_dependency_failure() -> None:
    foundation = SpeakerAttributionFoundation()
    generator = IdentityContextGenerator()
    runtime = _runtime_fixture(include_model_provider=False)
    request = create_attribution_request({"audio_ref": "sample_audio_001"})

    attribution = await foundation.attribute(
        entry_id="entry_1",
        runtime=runtime.runtime,
        request=request,
        services_registered=True,
    )
    context = generator.generate(attribution=attribution)

    assert attribution.status is not AttributionStatus.READY
    assert context.state in {"unavailable", "unknown", "low_confidence"}
    assert context.state != "known"


@pytest.mark.asyncio
async def test_fault_compatibility_validation_failure_paths_are_deterministic() -> None:
    manager = _model_config_manager()
    operation = GetCapabilitiesOperation.create(
        capability_registry=VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    )

    incompatible = await operation.evaluate_compatibility(
        request=CompatibilityDiscoveryRequest.create(
            requested_contract_version=99,
            requested_schema_version=99,
        )
    )

    assert incompatible.success is True
    assert incompatible.compatibility_status is CompatibilityStatus.UNSUPPORTED
    assert incompatible.compatibility_details.upgrade_guidance == "select_supported_versions"
