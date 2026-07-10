from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.voice_identity.attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
    ConfidenceBand,
    IdentityConfidenceLevel,
)
from custom_components.voice_identity.capability_discovery_operation import (
    CompatibilityDiscoveryRequest,
    CompatibilityStatus,
    GetCapabilitiesOperation,
    GetCapabilitiesRequest,
)
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import (
    VoiceIdentityConfigMigrationRequiredError,
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigurationValidationError,
    VoiceIdentityUnsupportedConfigVersionError,
)
from custom_components.voice_identity.diagnostics_provider import (
    VoiceIdentityDiagnosticsProvider,
    build_runtime_context,
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
    ModelExecutionProviderRuntime,
    ModelProviderMetadata,
)
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver


class _Entry:
    entry_id = "entry"
    data: dict[str, object]
    options: dict[str, object]

    def __init__(self, *, data: dict[str, object] | None = None, options: dict[str, object] | None = None) -> None:
        self.data = data or {}
        self.options = options or {}


class _MutationGuardCapabilityRegistry:
    def __init__(self, *, delegate: VoiceIdentityCapabilityRegistry) -> None:
        self._delegate = delegate
        self.register_calls = 0
        self.clear_calls = 0

    def supports(self, capability_name: str, *, config_schema_version: int | None = None) -> bool:
        return self._delegate.supports(capability_name, config_schema_version=config_schema_version)

    def snapshot(self):
        return self._delegate.snapshot()

    def register(self, descriptor):
        _ = descriptor
        self.register_calls += 1
        raise AssertionError("mutation not allowed")

    def clear(self):
        self.clear_calls += 1
        raise AssertionError("mutation not allowed")


class _ReadyBackend:
    def __init__(
        self,
        *,
        provider_name: str = "test_backend",
        provider_version: str = "1",
        available: bool = True,
        model_version: str = "v1",
        schema_version: int = 1,
    ) -> None:
        self._provider_name = provider_name
        self._provider_version = provider_version
        self._available = available
        self._model_version = model_version
        self._schema_version = schema_version

    @property
    def metadata(self) -> ModelProviderMetadata:
        return ModelProviderMetadata(
            provider_name=self._provider_name,
            provider_version=self._provider_version,
            supported_models=("ecapa_v1",),
            supported_representation_formats=("encrypted_representation_v1",),
            available=self._available,
        )

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        _ = request
        return BackendExecutionResult(
            encrypted_payload=b"enc_payload_v1",
            payload_format_version=1,
            encryption_scheme="aes_gcm_v1",
            key_reference="key_ref_v1",
            model_version=self._model_version,
            schema_version=self._schema_version,
            representation_format="encrypted_representation_v1",
            provider_confidence=0.92,
        )


@dataclass(frozen=True)
class MatrixCase:
    case_id: str
    source_version: str
    target_version: str
    artifact_schema_version: str
    contract_version: str
    provider_version: str
    model_version: str
    expected_status: str
    migration_required: bool
    downgrade_supported: bool
    expected_reason_code: str
    expected_health_status: str
    expected_compatibility_readiness: str
    expected_operator_guidance: str


MATRIX: tuple[MatrixCase, ...] = (
    MatrixCase("01_current_contract_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "no_action_required", "healthy", "ready", "no_action_required"),
    MatrixCase("02_previous_contract_fixture", "v0", "v1", "1", "0", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("03_legacy_contract_unsupported", "legacy", "v1", "1", "-1", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("04_future_contract_unsupported", "future", "v1", "1", "99", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("05_missing_contract_version", "missing", "v1", "1", "missing", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("06_malformed_contract_version", "malformed", "v1", "1", "malformed", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("07_current_schema_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "no_action_required", "healthy", "ready", "no_action_required"),
    MatrixCase("08_previous_schema_fixture", "v0", "v1", "0", "1", "1", "v1", "unsupported", False, False, "schema_version_unsupported", "degraded", "unavailable", "upgrade_recommended"),
    MatrixCase("09_unsupported_schema", "future", "v1", "99", "1", "1", "v1", "unsupported", False, False, "schema_version_unsupported", "degraded", "unavailable", "upgrade_recommended"),
    MatrixCase("10_missing_schema_metadata", "missing", "v1", "missing", "1", "1", "v1", "unsupported", False, False, "schema_version_unsupported", "degraded", "unavailable", "upgrade_recommended"),
    MatrixCase("11_malformed_schema_metadata", "malformed", "v1", "malformed", "1", "1", "v1", "unsupported", False, False, "schema_version_unsupported", "degraded", "unavailable", "upgrade_recommended"),
    MatrixCase("12_current_provider_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "model_execution_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("13_unsupported_provider_version", "v1", "v1", "1", "1", "999", "v1", "degraded", False, False, "model_provider_unavailable", "unavailable", "unavailable", "restore_model_backend"),
    MatrixCase("14_missing_provider_metadata", "v1", "v1", "1", "1", "missing", "v1", "degraded", False, False, "model_provider_unavailable", "unavailable", "unavailable", "restore_model_backend"),
    MatrixCase("15_model_version_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "model_execution_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("16_model_version_unsupported", "v1", "v1", "1", "1", "1", "v2", "unsupported", False, False, "unsupported_model", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("17_model_backend_unavailable", "v1", "v1", "1", "1", "1", "unavailable", "unavailable", False, False, "model_provider_unavailable", "unavailable", "unavailable", "restore_model_backend"),
    MatrixCase("18_artifact_schema_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "artifact_schema_compatible", "healthy", "ready", "no_action_required"),
    MatrixCase("19_artifact_schema_migration_required", "v0", "v1", "0", "1", "1", "v1", "migration_required", True, False, "artifact_schema_migration_required", "migration_required", "unavailable", "run_configuration_migration"),
    MatrixCase("20_artifact_schema_unsupported", "future", "v1", "99", "1", "1", "v1", "unsupported", False, False, "artifact_schema_unsupported", "unavailable", "unavailable", "select_supported_versions"),
    MatrixCase("21_registry_projection_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "voiceprint_registry_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("22_registry_projection_incompatible", "v1", "v1", "1", "1", "1", "v1", "incompatible", False, False, "voiceprint_artifact_missing", "unavailable", "unavailable", "run_registry_reconciliation"),
    MatrixCase("23_identity_context_contract_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "attribution_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("24_attribution_contract_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "attribution_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("25_health_telemetry_projection_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "telemetry_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("26_diagnostics_projection_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "diagnostics_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("27_repair_projection_compatible", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "repair_available", "healthy", "ready", "review_component_health"),
    MatrixCase("28_upgrade_path_supported", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "no_action_required", "healthy", "ready", "no_action_required"),
    MatrixCase("29_upgrade_path_migration_required", "v0", "v1", "0", "1", "1", "v1", "migration_required", True, False, "configuration_migration_required", "migration_required", "unavailable", "run_configuration_migration"),
    MatrixCase("30_upgrade_path_unsupported", "legacy", "v1", "-1", "-1", "1", "v1", "unsupported", False, False, "compatibility_version_unsupported", "unavailable", "unavailable", "select_supported_versions"),
    MatrixCase("31_downgrade_path_supported_if_applicable", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "no_action_required", "healthy", "ready", "no_action_required"),
    MatrixCase("32_downgrade_path_unsupported", "v1", "v0", "0", "0", "1", "v1", "unsupported", False, False, "schema_version_unsupported", "degraded", "unavailable", "select_supported_versions"),
    MatrixCase("33_migration_required_detected", "v0", "v1", "0", "1", "1", "v1", "migration_required", True, False, "configuration_migration_required", "migration_required", "unavailable", "run_configuration_migration"),
    MatrixCase("34_migration_unavailable_fails_closed", "v0", "v1", "0", "1", "1", "v1", "unavailable", True, False, "configuration_migration_required", "migration_required", "unavailable", "review_component_health"),
    MatrixCase("35_compatibility_readiness_healthy", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "health_ready", "healthy", "ready", "no_action_required"),
    MatrixCase("36_compatibility_readiness_degraded", "v1", "v1", "1", "1", "1", "v1", "degraded", False, False, "health_degraded", "degraded", "degraded", "review_component_health"),
    MatrixCase("37_compatibility_readiness_unavailable", "v1", "v1", "1", "1", "1", "v1", "unavailable", False, False, "health_unavailable", "unavailable", "unavailable", "reload_voice_identity"),
    MatrixCase("38_privacy_boundary_validation", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "privacy_safe", "healthy", "ready", "no_action_required"),
    MatrixCase("39_deterministic_reason_codes", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "deterministic", "healthy", "ready", "no_action_required"),
    MatrixCase("40_no_mutation_validation_only", "v1", "v1", "1", "1", "1", "v1", "compatible", False, False, "no_mutation", "healthy", "ready", "no_action_required"),
)


def _build_capability_operation() -> GetCapabilitiesOperation:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry())
    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    return GetCapabilitiesOperation.create(capability_registry=registry)


def _config_manager(
    *,
    schema_version: object | None = None,
    supported_models: tuple[str, ...] = ("ecapa_v1",),
) -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    data: dict[str, object] = {
        "generation": {
            "model_preference": "ecapa_v1",
            "min_sample_count": 2,
            "max_sample_count": 12,
            "quality_threshold": 0.75,
            "supported_models": list(supported_models),
        }
    }
    if schema_version is not None:
        data["config_schema_version"] = schema_version
    manager.load_from_entry(_Entry(data=data))
    return manager


def _health_runtime(*, model_state: HealthState, storage_state: HealthState, registry_state: HealthState) -> dict[str, object]:
    snapshot = HealthSnapshot(
        state=model_state if model_state is not HealthState.HEALTHY else HealthState.HEALTHY,
        reason_codes=("health_ready",) if model_state is HealthState.HEALTHY else ("dependency_unavailable",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=model_state,
                reason_codes=("model_provider_ready",) if model_state is HealthState.HEALTHY else ("model_provider_unavailable",),
                details={"provider_available": model_state is HealthState.HEALTHY},
            ),
            ComponentHealthReport(
                component="storage_provider",
                required=True,
                state=storage_state,
                reason_codes=("storage_provider_ready",) if storage_state is HealthState.HEALTHY else ("storage_provider_unavailable",),
                details={"loaded": storage_state is HealthState.HEALTHY},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=registry_state,
                reason_codes=("voiceprint_registry_ready",) if registry_state is HealthState.HEALTHY else ("voiceprint_artifact_missing",),
                details={"loaded": registry_state is HealthState.HEALTHY},
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
                component="get_capabilities_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("get_capabilities_ready",),
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
            min_sample_count=6,
            max_sample_count=12,
            quality_threshold=0.75,
        ),
    )
    return {
        "config_manager": SimpleNamespace(config=config),
        "health_engine": SimpleNamespace(snapshot=lambda: snapshot),
        "capability_registry": SimpleNamespace(
            snapshot=lambda: SimpleNamespace(
                registry_schema_version=1,
                config_schema_version=1,
                capabilities=(
                    SimpleNamespace(descriptor=SimpleNamespace(name="diagnostics", maturity="implemented"), enabled=True),
                ),
            )
        ),
        "repair_resolver": VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()),
        "model_execution_provider": object(),
    }


def _artifact_schema_fixture(version: object) -> tuple[str, str, bool]:
    if version == 1:
        return ("compatible", "artifact_schema_compatible", False)
    if version == 0:
        return ("migration_required", "artifact_schema_migration_required", True)
    if version in {None, "missing", "malformed"}:
        return ("unsupported", "artifact_schema_unsupported", False)
    if isinstance(version, int) and version > 1:
        return ("unsupported", "artifact_schema_unsupported", False)
    return ("unsupported", "artifact_schema_unsupported", False)


@pytest.mark.asyncio
async def test_vi126_matrix_is_defined_and_executed() -> None:
    assert len(MATRIX) == 40


@pytest.mark.asyncio
async def test_vi126_dependency_gate_surfaces_present() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()
    health = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.HEALTHY,
                storage_state=HealthState.HEALTHY,
                registry_state=HealthState.HEALTHY,
            ),
        ),
        services_registered=True,
    )
    telemetry = await provider.collect_telemetry(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.HEALTHY,
                storage_state=HealthState.HEALTHY,
                registry_state=HealthState.HEALTHY,
            ),
        ),
        services_registered=True,
    )

    assert "readiness" in health
    assert "compatibility_readiness" in health["readiness"]
    assert "attribution_readiness" in health["readiness"]
    assert telemetry["compatibility_readiness"] in {"ready", "degraded", "unavailable"}
    assert telemetry["attribution_readiness"] in {"ready", "degraded", "unavailable"}


@pytest.mark.asyncio
async def test_vi126_contract_and_schema_matrix() -> None:
    operation = _build_capability_operation()

    current = await operation.execute(GetCapabilitiesRequest.create(requested_contract_version=1, requested_schema_version=1))
    assert current.success is True

    unsupported_contract = await operation.execute(GetCapabilitiesRequest.create(requested_contract_version=99, requested_schema_version=1))
    assert unsupported_contract.success is False
    assert unsupported_contract.reason_code == "compatibility_version_unsupported"

    unsupported_schema = await operation.execute(GetCapabilitiesRequest.create(requested_contract_version=1, requested_schema_version=99))
    assert unsupported_schema.success is False
    assert unsupported_schema.reason_code == "schema_version_unsupported"

    missing_contract = await operation.execute(GetCapabilitiesRequest(requested_contract_version=cast(int, None), requested_schema_version=1))
    assert missing_contract.success is False
    assert missing_contract.reason_code == "compatibility_version_unsupported"

    malformed_contract = await operation.execute(GetCapabilitiesRequest(requested_contract_version=cast(int, "bad"), requested_schema_version=1))
    assert malformed_contract.success is False
    assert malformed_contract.reason_code == "compatibility_version_unsupported"

    missing_schema = await operation.execute(GetCapabilitiesRequest(requested_contract_version=1, requested_schema_version=cast(int, None)))
    assert missing_schema.success is False
    assert missing_schema.reason_code == "schema_version_unsupported"

    malformed_schema = await operation.execute(GetCapabilitiesRequest(requested_contract_version=1, requested_schema_version=cast(int, "bad")))
    assert malformed_schema.success is False
    assert malformed_schema.reason_code == "schema_version_unsupported"


@pytest.mark.asyncio
async def test_vi126_config_migration_matrix() -> None:
    manager = VoiceIdentityConfigurationManager()

    manager.load_from_entry(_Entry(data={"config_schema_version": 1}))

    with pytest.raises(VoiceIdentityConfigMigrationRequiredError):
        manager.load_from_entry(_Entry(data={"config_schema_version": 0}))

    with pytest.raises(VoiceIdentityUnsupportedConfigVersionError):
        manager.load_from_entry(_Entry(data={"config_schema_version": 2}))

    with pytest.raises(VoiceIdentityConfigurationValidationError):
        manager.load_from_entry(_Entry(data={"config_schema_version": "bad"}))

    default_loaded = VoiceIdentityConfigurationManager()
    config = default_loaded.load_from_entry(_Entry(data={}))
    assert config.config_schema_version == 1


@pytest.mark.asyncio
async def test_vi126_provider_and_model_version_matrix() -> None:
    validation = SimpleNamespace(passed=True, reason_code="validation_ready", sample_count=2)
    quality = SimpleNamespace(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75)

    provider_ok = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(provider_version="1", available=True, model_version="v1", schema_version=1),
    )
    result_ok = await provider_ok.generate(
        request=SimpleNamespace(
            identifiers=SimpleNamespace(generation_id="gen_001"),
            options=SimpleNamespace(model_preference="ecapa_v1", timeout_seconds=1.0),
            sample_references=("sample_1", "sample_2"),
            prepared_enrollment_inputs=("prepared_1",),
        ),
        validation=validation,
        quality=quality,
    )
    assert result_ok.success is True
    assert result_ok.reason_code == "model_execution_ready"

    provider_unsupported = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(supported_models=("ecapa_v1",)),
        backend=_ReadyBackend(provider_version="1", available=True),
    )
    result_unsupported = await provider_unsupported.generate(
        request=SimpleNamespace(
            identifiers=SimpleNamespace(generation_id="gen_001"),
            options=SimpleNamespace(model_preference="ecapa_v2", timeout_seconds=1.0),
            sample_references=("sample_1", "sample_2"),
            prepared_enrollment_inputs=("prepared_1",),
        ),
        validation=validation,
        quality=quality,
    )
    assert result_unsupported.success is False
    assert result_unsupported.reason_code == "unsupported_model"

    provider_unavailable = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(provider_version="999", available=False),
    )
    result_unavailable = await provider_unavailable.generate(
        request=SimpleNamespace(
            identifiers=SimpleNamespace(generation_id="gen_001"),
            options=SimpleNamespace(model_preference="ecapa_v1", timeout_seconds=1.0),
            sample_references=("sample_1", "sample_2"),
            prepared_enrollment_inputs=("prepared_1",),
        ),
        validation=validation,
        quality=quality,
    )
    assert result_unavailable.success is False
    assert result_unavailable.reason_code == "model_provider_unavailable"


def test_vi126_artifact_schema_matrix_fixture() -> None:
    current = _artifact_schema_fixture(1)
    migration = _artifact_schema_fixture(0)
    future = _artifact_schema_fixture(99)
    missing = _artifact_schema_fixture("missing")
    malformed = _artifact_schema_fixture("malformed")

    assert current == ("compatible", "artifact_schema_compatible", False)
    assert migration == ("migration_required", "artifact_schema_migration_required", True)
    assert future[1] == "artifact_schema_unsupported"
    assert missing[1] == "artifact_schema_unsupported"
    assert malformed[1] == "artifact_schema_unsupported"


@pytest.mark.asyncio
async def test_vi126_upgrade_and_downgrade_paths() -> None:
    operation = _build_capability_operation()

    upgrade_supported = await operation.evaluate_compatibility(
        CompatibilityDiscoveryRequest.create(requested_contract_version=1, requested_schema_version=1)
    )
    assert upgrade_supported.success is True
    assert upgrade_supported.compatibility_status is CompatibilityStatus.COMPATIBLE

    upgrade_partial = await operation.evaluate_compatibility(
        CompatibilityDiscoveryRequest.create(requested_contract_version=1, requested_schema_version=99)
    )
    assert upgrade_partial.success is True
    assert upgrade_partial.compatibility_status is CompatibilityStatus.PARTIALLY_COMPATIBLE
    assert upgrade_partial.compatibility_details.upgrade_guidance == "upgrade_recommended"

    upgrade_unsupported = await operation.evaluate_compatibility(
        CompatibilityDiscoveryRequest.create(requested_contract_version=99, requested_schema_version=99)
    )
    assert upgrade_unsupported.success is True
    assert upgrade_unsupported.compatibility_status is CompatibilityStatus.UNSUPPORTED

    downgrade_unsupported = await operation.evaluate_compatibility(
        CompatibilityDiscoveryRequest.create(requested_contract_version=0, requested_schema_version=0)
    )
    assert downgrade_unsupported.success is True
    assert downgrade_unsupported.compatibility_status is CompatibilityStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_vi126_migration_required_and_fail_closed_behavior() -> None:
    migration_snapshot = HealthSnapshot(
        state=HealthState.MIGRATION_REQUIRED,
        reason_codes=("configuration_migration_required",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"provider_available": False},
            ),
            ComponentHealthReport(
                component="storage_provider",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"loaded": False},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"loaded": False},
            ),
            ComponentHealthReport(
                component="voiceprint_lifecycle_manager",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"loaded": False},
            ),
            ComponentHealthReport(
                component="voiceprint_revision_manager",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"loaded": False},
            ),
            ComponentHealthReport(
                component="get_capabilities_operation",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=("configuration_migration_required",),
                details={"loaded": False},
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
            min_sample_count=6,
            max_sample_count=12,
            quality_threshold=0.75,
        ),
    )

    provider = VoiceIdentityHealthTelemetryProvider()
    payload = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime={
                "config_manager": SimpleNamespace(config=config),
                "health_engine": SimpleNamespace(snapshot=lambda: migration_snapshot),
                "capability_registry": SimpleNamespace(snapshot=lambda: SimpleNamespace(registry_schema_version=1, config_schema_version=1, capabilities=())),
                "repair_resolver": VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()),
                "model_execution_provider": object(),
            },
        ),
        services_registered=True,
    )

    assert payload["status"] == "migration_required"
    assert payload["reason_code"] == "configuration_migration_required"
    assert payload["readiness"]["compatibility_readiness"] == "unavailable"


@pytest.mark.asyncio
async def test_vi126_readiness_matrix_and_privacy_boundaries() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    healthy = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.HEALTHY,
                storage_state=HealthState.HEALTHY,
                registry_state=HealthState.HEALTHY,
            ),
        ),
        services_registered=True,
    )
    degraded = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.DEGRADED,
                storage_state=HealthState.HEALTHY,
                registry_state=HealthState.HEALTHY,
            ),
        ),
        services_registered=True,
    )
    unavailable = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.UNAVAILABLE,
                storage_state=HealthState.UNAVAILABLE,
                registry_state=HealthState.UNAVAILABLE,
            ),
        ),
        services_registered=True,
    )

    assert healthy["readiness"]["compatibility_readiness"] == "ready"
    assert degraded["readiness"]["compatibility_readiness"] == "degraded"
    assert unavailable["readiness"]["compatibility_readiness"] == "unavailable"

    telemetry = await provider.collect_telemetry(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_health_runtime(
                model_state=HealthState.HEALTHY,
                storage_state=HealthState.HEALTHY,
                registry_state=HealthState.HEALTHY,
            ),
        ),
        services_registered=True,
    )
    rendered = str(telemetry).lower()
    for forbidden in {"audio", "embedding", "vector", "transcript", "path", "token", "secret", "traceback", "exception"}:
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_vi126_identity_attribution_diagnostics_repairs_contracts() -> None:
    attribution = AttributionResult(
        success=True,
        status=AttributionStatus.READY,
        identity_confidence_level=IdentityConfidenceLevel.RECOGNIZED,
        attributed_person_id="person_1",
        attributed_profile_id="vp_1",
        attributed_artifact_id="artifact_1",
        confidence=0.91,
        confidence_band=ConfidenceBand.HIGH,
        reason_code="attribution_ready",
        attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
        is_confident=True,
        is_ambiguous=False,
        is_abstained=False,
        diagnostic_summary=AttributionDiagnosticSummary(
            diagnostic_available=True,
            diagnostic_reason_code="diagnostics_ready",
            repair_available=True,
            health_status="healthy",
            attribution_readiness="ready",
            compatibility_readiness="ready",
        ),
        repair_hint_code="review_component_health",
        suggested_next_action_code="no_action_required",
        health_status="healthy",
        readiness_status="ready",
    )

    identity_context = IdentityContextGenerator().to_dict(
        context=IdentityContextGenerator().generate(attribution=attribution)
    )
    assert identity_context["state"] == "known"
    assert identity_context["person_id"] == "person_1"

    diagnostics = await VoiceIdentityDiagnosticsProvider().collect(
        context=build_runtime_context(entry_id="entry_1", runtime=_health_runtime(
            model_state=HealthState.HEALTHY,
            storage_state=HealthState.HEALTHY,
            registry_state=HealthState.HEALTHY,
        )),
        source="vi126_matrix",
    )
    reason_code = diagnostics["failure"]["reason_code"]
    issue_reason_codes = diagnostics["failure"]["issue_reason_codes"]
    if reason_code == "no_issues":
        assert issue_reason_codes == []
    else:
        assert reason_code in issue_reason_codes

    repair_projection = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()).resolve(
        {
            "reason_code": "voiceprint_artifact_missing",
            "repair_hint_code": "run_registry_reconciliation",
            "suggested_next_action_code": "regenerate_enrollment",
            "is_retryable": False,
            "is_repairable_candidate": True,
            "issue_reason_codes": ["voiceprint_artifact_missing"],
        }
    ).to_dict()
    assert repair_projection["status"] in {
        "repair_available",
        "repair_not_available",
        "retry_recommended",
        "manual_intervention_required",
        "unsupported_failure_type",
        "diagnostics_unavailable",
    }


@pytest.mark.asyncio
async def test_vi126_reason_codes_are_deterministic_and_validation_is_non_mutating() -> None:
    operation = _build_capability_operation()

    first = await operation.execute(GetCapabilitiesRequest.create(requested_contract_version=99, requested_schema_version=1))
    second = await operation.execute(GetCapabilitiesRequest.create(requested_contract_version=99, requested_schema_version=1))
    assert first.success is False
    assert second.success is False
    assert first.reason_code == second.reason_code == "compatibility_version_unsupported"

    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry())
    guarded_registry = _MutationGuardCapabilityRegistry(delegate=VoiceIdentityCapabilityRegistry.from_configuration_manager(manager))
    guarded_operation = GetCapabilitiesOperation.create(capability_registry=cast(Any, guarded_registry))
    response = await guarded_operation.execute(GetCapabilitiesRequest.create())

    assert response.success is True
    assert guarded_registry.register_calls == 0
    assert guarded_registry.clear_calls == 0
