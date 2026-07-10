from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.voice_identity.const import (
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_HEALTH_ENGINE,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_REPAIR_RESOLVER,
)
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState
from custom_components.voice_identity.health_telemetry import (
    VoiceIdentityHealthTelemetryProvider,
    build_health_telemetry_context,
)
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver


def _runtime(*, health_state: HealthState = HealthState.HEALTHY) -> dict[str, object]:
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
        state=health_state,
        reason_codes=("health_ready",) if health_state is HealthState.HEALTHY else ("dependency_unavailable",),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=health_state,
                reason_codes=("model_provider_unavailable",)
                if health_state is not HealthState.HEALTHY
                else ("model_provider_ready",),
                details={"provider": "backend_v1", "provider_available": health_state is HealthState.HEALTHY},
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_registry_ready",),
                details={"loaded": True, "record_count": 0},
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

    capability_registry = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            registry_schema_version=1,
            config_schema_version=1,
            capabilities=(
                SimpleNamespace(
                    descriptor=SimpleNamespace(name="diagnostics", maturity="implemented"),
                    enabled=True,
                ),
                SimpleNamespace(
                    descriptor=SimpleNamespace(name="health_service", maturity="implemented"),
                    enabled=True,
                ),
            ),
        )
    )

    repair_resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    return {
        DATA_CONFIG_MANAGER: SimpleNamespace(config=config),
        DATA_HEALTH_ENGINE: SimpleNamespace(snapshot=lambda: health),
        DATA_CAPABILITY_REGISTRY: capability_registry,
        DATA_MODEL_EXECUTION_PROVIDER: object(),
        DATA_REPAIR_RESOLVER: repair_resolver,
    }


@pytest.mark.asyncio
async def test_health_telemetry_provider_collects_health() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    payload = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=_runtime()),
        services_registered=True,
    )

    assert payload["entry_id"] == "entry_1"
    assert payload["status"] == "healthy"
    assert payload["diagnostic_available"] is True
    assert payload["readiness"]["attribution_readiness"] == "ready"
    assert payload["readiness"]["compatibility_readiness"] == "ready"


@pytest.mark.asyncio
async def test_health_telemetry_provider_collects_degraded_health() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    payload = await provider.collect_health(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_runtime(health_state=HealthState.DEGRADED),
        ),
        services_registered=True,
    )

    assert payload["status"] == "degraded"
    assert payload["reason_code"] in {
        "dependency_unavailable",
        "health_degraded",
        "model_provider_unavailable",
    }


@pytest.mark.asyncio
async def test_health_telemetry_provider_collects_telemetry_projection() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    payload = await provider.collect_telemetry(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=_runtime()),
        services_registered=True,
    )

    assert payload["status"] == "telemetry_ready"
    assert payload["reason_code"] == "telemetry_ready"
    assert isinstance(payload["component_status"], list)
    assert payload["capability_status"]["available"] is True


@pytest.mark.asyncio
async def test_health_telemetry_provider_reports_degraded_when_runtime_unavailable() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    payload = await provider.collect_telemetry(
        context=build_health_telemetry_context(
            entry_id="entry_1",
            runtime=_runtime(health_state=HealthState.UNAVAILABLE),
        ),
        services_registered=True,
    )

    assert payload["status"] == "telemetry_degraded"
    assert payload["reason_code"] == "telemetry_degraded"


@pytest.mark.asyncio
async def test_health_telemetry_provider_fails_closed_when_unloaded() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()
    provider.clear()

    payload = await provider.collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=_runtime()),
        services_registered=False,
    )

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "health_unavailable"


@pytest.mark.asyncio
async def test_health_telemetry_privacy_boundaries() -> None:
    provider = VoiceIdentityHealthTelemetryProvider()

    payload = await provider.collect_telemetry(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=_runtime()),
        services_registered=True,
    )

    serialized = str(payload).lower()
    for forbidden in {
        "audio",
        "embedding",
        "vector",
        "transcript",
        "secret",
        "token",
        "path",
        "traceback",
        "exception",
    }:
        assert forbidden not in serialized
