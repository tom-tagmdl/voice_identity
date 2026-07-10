from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.attribution_service import SpeakerAttributionFoundation
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
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
from custom_components.voice_identity.health_telemetry import VoiceIdentityHealthTelemetryProvider
from custom_components.voice_identity.identity_context import IdentityContextGenerator
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver
from custom_components.voice_identity.services import (
    SERVICE_ATTRIBUTE_SPEAKER,
    SERVICE_GET_DIAGNOSTICS,
    SERVICE_GET_HEALTH,
    SERVICE_GET_IDENTITY_CONTEXT,
    SERVICE_GET_REPAIRS,
    SERVICE_GET_TELEMETRY,
    async_register_services,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-129-release-readiness-and-operational-runbook.md"


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

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._handlers

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


def _model_config_manager() -> VoiceIdentityConfigurationManager:
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
    manager.load_from_entry(_Entry(data=data))
    return manager


def _health_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        state=HealthState.HEALTHY,
        reason_codes=("health_ready",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("model_provider_ready",),
                details={"provider_available": True},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_registry_ready",),
                details={"loaded": True, "record_count": 1},
            ),
            ComponentHealthReport(
                component="storage_provider",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("storage_provider_ready",),
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


def _runtime_fixture() -> dict[str, object]:
    manager = _model_config_manager()
    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    return {
        DATA_CONFIG_MANAGER: manager,
        DATA_HEALTH_ENGINE: SimpleNamespace(snapshot=_health_snapshot),
        DATA_CAPABILITY_REGISTRY: registry,
        DATA_VOICEPRINT_REGISTRY: _Registry([_record("vp_001", "artifact_001", "person_001")]),
        DATA_VOICEPRINT_LIFECYCLE_MANAGER: object(),
        DATA_VOICEPRINT_REVISION_MANAGER: object(),
        DATA_GENERATION_ORCHESTRATOR: object(),
        DATA_GENERATE_VOICEPRINT_OPERATION: object(),
        DATA_GET_VOICEPRINT_STATUS_OPERATION: object(),
        DATA_GET_CAPABILITIES_OPERATION: object(),
        DATA_HEALTH_TELEMETRY_PROVIDER: VoiceIdentityHealthTelemetryProvider(),
        DATA_ATTRIBUTION_FOUNDATION: SpeakerAttributionFoundation(),
        DATA_IDENTITY_CONTEXT_GENERATOR: IdentityContextGenerator(),
        DATA_MODEL_EXECUTION_PROVIDER: object(),
        DATA_REPAIR_RESOLVER: VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()),
    }


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8").lower()


def test_dependency_gate_completeness_surfaces_present() -> None:
    required_suite_paths = {
        REPO_ROOT / "tests" / "test_diagnostics_provider.py",
        REPO_ROOT / "tests" / "test_repairs.py",
        REPO_ROOT / "tests" / "test_health_telemetry.py",
        REPO_ROOT / "tests" / "test_attribution_foundation.py",
        REPO_ROOT / "tests" / "test_identity_context.py",
        REPO_ROOT / "tests" / "test_compatibility_migration_matrix.py",
        REPO_ROOT / "tests" / "test_performance_resource_hardening.py",
        REPO_ROOT / "tests" / "test_fault_injection_and_recovery.py",
    }
    required_doc_paths = {
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-121-diagnostics-provider.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-122-repair-framework.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-123-speaker-attribution-foundation.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-124-identity-context-generation.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-125-health-and-telemetry-integration.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-126-compatibility-and-migration-test-matrix.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-127-performance-and-resource-hardening.md",
        REPO_ROOT / "docs" / "architecture" / "voice_identity" / "vi-128-fault-injection-and-recovery-hardening.md",
    }

    for path in required_suite_paths | required_doc_paths:
        assert path.exists(), f"Missing dependency gate artifact: {path}"


def test_capability_registry_completeness_for_release_surfaces() -> None:
    manager = _model_config_manager()
    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    snapshot = registry.snapshot()
    capability_names = {item.descriptor.name for item in snapshot.capabilities}

    for required in {
        "capability_registry",
        "capability_discovery_operation",
        "runtime_attribution",
        "identity_context_generation",
        "health_state_engine",
        "diagnostics",
        "repairs",
        "discovery_contract_versions",
        "discovery_feature_availability",
    }:
        assert required in capability_names


@pytest.mark.asyncio
async def test_required_service_registrations_present() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}

    await async_register_services(hass)

    for service_name in {
        SERVICE_GET_DIAGNOSTICS,
        SERVICE_GET_REPAIRS,
        SERVICE_GET_HEALTH,
        SERVICE_GET_TELEMETRY,
        SERVICE_ATTRIBUTE_SPEAKER,
        SERVICE_GET_IDENTITY_CONTEXT,
    }:
        assert hass.services.has_service(DOMAIN, service_name)


@pytest.mark.asyncio
async def test_required_readiness_surfaces_present() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    health = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {"entry_id": "entry"},
        return_response=True,
    )
    telemetry = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert health["success"] is True
    assert telemetry["success"] is True
    assert "readiness" in health["health"]
    assert "attribution_readiness" in health["health"]["readiness"]
    assert "compatibility_readiness" in health["health"]["readiness"]
    assert "attribution_readiness" in telemetry["telemetry"]
    assert "compatibility_readiness" in telemetry["telemetry"]


@pytest.mark.asyncio
async def test_diagnostics_availability() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    diagnostics = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_DIAGNOSTICS,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert diagnostics["success"] is True
    assert diagnostics["reason_code"] == "ready"
    assert diagnostics["diagnostics"]["failure"]["reason_code"] in {
        "no_issues",
        "healthy",
        "degraded",
        "unavailable",
    }


@pytest.mark.asyncio
async def test_repair_availability() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    repairs = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_REPAIRS,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert repairs["success"] is True
    assert repairs["reason_code"] == "ready"
    assert repairs["repairs"]["status"] in {
        "repair_available",
        "repair_not_available",
        "retry_recommended",
        "manual_intervention_required",
        "unsupported_failure_type",
        "diagnostics_unavailable",
    }


@pytest.mark.asyncio
async def test_health_availability() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["health"]["status"] in {"healthy", "degraded", "unavailable"}


@pytest.mark.asyncio
async def test_telemetry_availability() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["telemetry"]["status"] in {
        "telemetry_ready",
        "telemetry_degraded",
        "telemetry_unavailable",
    }


@pytest.mark.asyncio
async def test_attribution_readiness_visibility() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["health"]["readiness"]["attribution_readiness"] in {"ready", "degraded", "unavailable"}


@pytest.mark.asyncio
async def test_compatibility_readiness_visibility() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {"entry": _runtime_fixture()}
    await async_register_services(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_HEALTH,
        {"entry_id": "entry"},
        return_response=True,
    )

    assert response["success"] is True
    assert response["health"]["readiness"]["compatibility_readiness"] in {
        "ready",
        "degraded",
        "unavailable",
    }


def test_runbook_documentation_presence() -> None:
    assert RUNBOOK_PATH.exists()
    content = _runbook_text()
    for required in {
        "release readiness criteria",
        "operational checklist",
        "deployment checklist",
        "verification steps",
        "diagnostics procedures",
        "repair procedures",
        "health procedures",
        "compatibility procedures",
        "recovery procedures",
        "escalation procedures",
        "supported operational workflows",
        "known limitations",
    }:
        assert required in content


def test_checklist_completeness() -> None:
    content = _runbook_text()
    for required in {
        "adr compliance verified",
        "ownership boundaries verified",
        "completed issue verification",
        "capability verification",
        "unit tests passing",
        "compatibility tests passing",
        "performance tests passing",
        "fault injection tests passing",
        "readiness validated",
        "diagnostics validated",
        "repairs validated",
        "privacy boundaries validated",
        "safe outputs validated",
        "architecture complete",
        "adrs complete",
        "runbook complete",
        "diagnostics documented",
        "repair workflows documented",
        "recovery workflows documented",
    }:
        assert required in content


def test_go_live_criteria_completeness() -> None:
    content = _runbook_text()
    for required in {
        "go-live decision matrix",
        "ready",
        "conditionally ready",
        "not ready",
        "tests pass",
        "readiness surfaces report healthy",
        "diagnostics show no critical failures",
        "compatibility baseline validated",
        "performance baseline validated",
        "resiliency baseline validated",
    }:
        assert required in content