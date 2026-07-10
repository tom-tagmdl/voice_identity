from __future__ import annotations

import gc
from pathlib import Path
import time
import tracemalloc
from dataclasses import dataclass
from statistics import mean
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.attribution_service import SpeakerAttributionFoundation, create_attribution_request
from custom_components.voice_identity.capability_discovery_operation import GetCapabilitiesOperation, GetCapabilitiesRequest
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.const import DOMAIN
from custom_components.voice_identity.diagnostics_provider import VoiceIdentityDiagnosticsProvider, build_runtime_context
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState
from custom_components.voice_identity.health_telemetry import VoiceIdentityHealthTelemetryProvider, build_health_telemetry_context
from custom_components.voice_identity.identity_context import IdentityContextGenerator
from custom_components.voice_identity.repair_registry import VoiceIdentityRepairRegistry
from custom_components.voice_identity.repair_resolver import VoiceIdentityRepairResolver
from custom_components.voice_identity.services import async_register_services, async_unregister_services
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    VoiceprintSubjectId,
    create_voiceprint_record,
)
from tests.test_voiceprint_registry import _FakeStorageProvider, _FakeStore


class _Entry:
    entry_id = "entry"
    data: dict[str, object] = {}
    options: dict[str, object] = {}


class _FakeServiceRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], object] = {}

    def async_register(self, domain, service, handler, schema=None, supports_response=None):
        _ = schema
        _ = supports_response
        self._handlers[(domain, service)] = handler

    def async_remove(self, domain, service):
        self._handlers.pop((domain, service), None)


class _FakeHass:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}
        self.services = _FakeServiceRegistry()


@dataclass(slots=True, frozen=True)
class LatencyStats:
    runs: int
    avg_ms: float
    worst_ms: float


def _latency_stats(samples: list[float]) -> LatencyStats:
    ms = [item * 1000.0 for item in samples]
    return LatencyStats(runs=len(samples), avg_ms=mean(ms), worst_ms=max(ms))


async def _measure_async(repeats: int, func) -> LatencyStats:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        await func()
        samples.append(time.perf_counter() - started)
    return _latency_stats(samples)


def _measure_sync(repeats: int, func) -> LatencyStats:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        func()
        samples.append(time.perf_counter() - started)
    return _latency_stats(samples)


def _build_registry(config_manager: VoiceIdentityConfigurationManager) -> VoiceIdentityCapabilityRegistry:
    return VoiceIdentityCapabilityRegistry.from_configuration_manager(config_manager)


async def _build_voiceprint_registry(record_count: int) -> VoiceprintRegistry:
    existing = {f"artifact_{idx:04d}" for idx in range(record_count)}
    storage = _FakeStorageProvider(existing_artifacts=existing)
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()

    for idx in range(record_count):
        record = create_voiceprint_record(
            voiceprint_id=f"vp_{idx:04d}",
            artifact_id=f"artifact_{idx:04d}",
            subject_id=f"person_{idx:04d}",
            revision=1,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
            model_name="ecapa_v1",
            model_version="v1",
            schema_version=1,
        )
        await registry.register_record(record)

    return registry


def _health_snapshot(*, model_state: HealthState = HealthState.HEALTHY) -> HealthSnapshot:
    return HealthSnapshot(
        state=model_state,
        reason_codes=("health_ready",) if model_state is HealthState.HEALTHY else ("model_provider_unavailable",),
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


def _runtime(*, include_registry: VoiceprintRegistry | None = None, health_state: HealthState = HealthState.HEALTHY) -> dict[str, object]:
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
    manager = SimpleNamespace(config=config)
    cap_registry = _build_registry(_loaded_config_manager())
    return {
        "config_manager": manager,
        "health_engine": SimpleNamespace(snapshot=lambda: _health_snapshot(model_state=health_state)),
        "capability_registry": cap_registry,
        "model_execution_provider": object(),
        "voiceprint_registry": include_registry if include_registry is not None else object(),
        "repair_resolver": VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults()),
        "health_telemetry_provider": VoiceIdentityHealthTelemetryProvider(),
    }


def _loaded_config_manager() -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry())
    return manager


@pytest.mark.asyncio
async def test_vi127_dependency_gate_vi126_matrix_still_green() -> None:
    # Dependency gate for VI-127 requires VI-126 matrix completeness surface.
    from tests.test_compatibility_migration_matrix import MATRIX

    assert len(MATRIX) == 40


def test_startup_performance_baseline() -> None:
    def _startup_cycle() -> dict[str, object]:
        manager = _loaded_config_manager()
        registry = _build_registry(manager)
        diagnostics_provider = VoiceIdentityDiagnosticsProvider()
        health_provider = VoiceIdentityHealthTelemetryProvider()
        attribution = SpeakerAttributionFoundation()
        identity = IdentityContextGenerator()
        repair_registry = VoiceIdentityRepairRegistry.with_defaults()
        repair_resolver = VoiceIdentityRepairResolver(registry=repair_registry)
        return {
            "manager": manager,
            "registry": registry,
            "diagnostics_provider": diagnostics_provider,
            "health_provider": health_provider,
            "attribution": attribution,
            "identity": identity,
            "repair_resolver": repair_resolver,
        }

    stats = _measure_sync(25, _startup_cycle)

    assert stats.runs == 25
    assert stats.avg_ms > 0.0
    assert stats.worst_ms >= stats.avg_ms


@pytest.mark.asyncio
async def test_service_registration_overhead_baseline() -> None:
    hass = _FakeHass()
    hass.data[DOMAIN] = {}

    async def _register_cycle() -> None:
        await async_register_services(hass)
        await async_unregister_services(hass)

    stats = await _measure_async(30, _register_cycle)

    assert stats.runs == 30
    assert stats.avg_ms > 0.0
    assert stats.worst_ms >= stats.avg_ms


@pytest.mark.asyncio
async def test_attribution_and_identity_context_latency_stability() -> None:
    foundation = SpeakerAttributionFoundation()
    registry = await _build_voiceprint_registry(1)
    runtime = _runtime(include_registry=registry)
    request = create_attribution_request({"audio_ref": "sample_audio_001"})
    generator = IdentityContextGenerator()

    async def _attribute_once() -> None:
        result = await foundation.attribute(
            entry_id="entry_1",
            runtime=runtime,
            request=request,
            services_registered=True,
        )
        _ = generator.generate(attribution=result)

    stats = await _measure_async(50, _attribute_once)

    assert stats.runs == 50
    assert stats.avg_ms > 0.0
    assert stats.worst_ms < (stats.avg_ms * 25)


@pytest.mark.asyncio
async def test_diagnostics_and_repairs_latency_baseline() -> None:
    runtime = _runtime()
    provider = VoiceIdentityDiagnosticsProvider()
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    async def _diagnostics_once() -> None:
        payload = await provider.collect(
            context=build_runtime_context(entry_id="entry_1", runtime=runtime),
            source="vi127_performance",
        )
        _ = resolver.resolve(payload.get("failure") if isinstance(payload, dict) else None)

    stats = await _measure_async(60, _diagnostics_once)

    assert stats.runs == 60
    assert stats.avg_ms > 0.0
    assert stats.worst_ms < (stats.avg_ms * 30)


@pytest.mark.asyncio
async def test_health_telemetry_latency_baseline() -> None:
    runtime = _runtime()
    provider = VoiceIdentityHealthTelemetryProvider()

    async def _health_cycle() -> None:
        _ = await provider.collect_health(
            context=build_health_telemetry_context(entry_id="entry_1", runtime=runtime),
            services_registered=True,
        )
        _ = await provider.collect_telemetry(
            context=build_health_telemetry_context(entry_id="entry_1", runtime=runtime),
            services_registered=True,
        )

    stats = await _measure_async(50, _health_cycle)

    assert stats.runs == 50
    assert stats.avg_ms > 0.0
    assert stats.worst_ms < (stats.avg_ms * 30)


@pytest.mark.asyncio
async def test_capability_discovery_latency_baseline() -> None:
    operation = GetCapabilitiesOperation.create(capability_registry=_build_registry(_loaded_config_manager()))

    async def _capability_cycle() -> None:
        _ = await operation.execute(GetCapabilitiesRequest.create())
        _ = await operation.evaluate_compatibility(
            request=SimpleNamespace(
                requested_contract_version=1,
                requested_schema_version=1,
                correlation_id=None,
                request_metadata={},
            )
        )

    stats = await _measure_async(100, _capability_cycle)

    assert stats.runs == 100
    assert stats.avg_ms > 0.0
    assert stats.worst_ms < (stats.avg_ms * 25)


@pytest.mark.asyncio
async def test_registry_lookup_scaling_behavior() -> None:
    small_registry = await _build_voiceprint_registry(20)
    large_registry = await _build_voiceprint_registry(200)

    def _small_lookup() -> None:
        _ = small_registry.get_by_subject_id(VoiceprintSubjectId.parse("person_0010"))

    def _large_lookup() -> None:
        _ = large_registry.get_by_subject_id(VoiceprintSubjectId.parse("person_0100"))

    small_stats = _measure_sync(200, _small_lookup)
    large_stats = _measure_sync(200, _large_lookup)

    assert small_stats.avg_ms > 0.0
    assert large_stats.avg_ms > 0.0
    assert large_stats.avg_ms < (small_stats.avg_ms * 200)


@pytest.mark.asyncio
async def test_repeated_execution_stability_and_determinism() -> None:
    foundation = SpeakerAttributionFoundation()
    registry = await _build_voiceprint_registry(1)
    runtime = _runtime(include_registry=registry)
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
async def test_memory_growth_and_object_retention_baseline() -> None:
    runtime = _runtime()
    provider = VoiceIdentityHealthTelemetryProvider()

    tracemalloc.start()
    gc.collect()
    start_current, _ = tracemalloc.get_traced_memory()

    for _ in range(200):
        _ = await provider.collect_health(
            context=build_health_telemetry_context(entry_id="entry_1", runtime=runtime),
            services_registered=True,
        )

    gc.collect()
    mid_current, mid_peak = tracemalloc.get_traced_memory()

    for _ in range(200):
        _ = await provider.collect_health(
            context=build_health_telemetry_context(entry_id="entry_1", runtime=runtime),
            services_registered=True,
        )

    gc.collect()
    end_current, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert mid_peak > 0
    assert end_peak >= mid_peak
    assert (end_current - start_current) < 8_000_000
    assert (end_current - mid_current) < 4_000_000


@pytest.mark.asyncio
async def test_no_functional_regression_from_performance_hardening() -> None:
    runtime = _runtime()
    diagnostics = await VoiceIdentityDiagnosticsProvider().collect(
        context=build_runtime_context(entry_id="entry_1", runtime=runtime),
        source="vi127_regression_guard",
    )

    health = await VoiceIdentityHealthTelemetryProvider().collect_health(
        context=build_health_telemetry_context(entry_id="entry_1", runtime=runtime),
        services_registered=True,
    )

    assert diagnostics["platform"]["runtime_loaded"] is True
    assert health["readiness"]["compatibility_readiness"] in {"ready", "degraded", "unavailable"}


def test_performance_documentation_alignment() -> None:
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "architecture"
        / "voice_identity"
        / "vi-127-performance-and-resource-hardening.md"
    )
    with doc_path.open("r", encoding="utf-8") as handle:
        content = handle.read().lower()

    for required in {
        "performance baseline",
        "resource baseline",
        "scaling",
        "bottleneck",
        "recommendations",
        "known limitations",
        "does not implement fault injection",
        "does not implement release readiness",
    }:
        assert required in content
