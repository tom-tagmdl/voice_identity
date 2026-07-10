from __future__ import annotations

import pytest

from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import (
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigMigrationRequiredError,
)
from custom_components.voice_identity.health_state import (
    HealthReasonCode,
    HealthState,
    VoiceIdentityHealthStateEngine,
    VoiceIdentityUnsafeDetailsError,
    VoiceIdentityUnsafeReasonCodeError,
)


class _Entry:
    entry_id = "entry"
    data: dict[str, object] = {}
    options: dict[str, object] = {}


def _build_foundation() -> tuple[
    VoiceIdentityConfigurationManager,
    VoiceIdentityCapabilityRegistry,
]:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry())
    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    return manager, registry


def test_healthy_aggregation() -> None:
    manager, registry = _build_foundation()

    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )
    snapshot = engine.snapshot()

    assert snapshot.state is HealthState.HEALTHY
    assert snapshot.reason_codes == ()


def test_degraded_aggregation_with_optional_degraded_component() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="future_storage_probe",
        required=False,
        state=HealthState.DEGRADED,
        reason_codes=("dependency_unavailable",),
    )

    snapshot = engine.snapshot()
    assert snapshot.state is HealthState.DEGRADED
    assert "dependency_unavailable" in snapshot.reason_codes


def test_unavailable_aggregation_with_required_component() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="model_provider",
        required=True,
        state=HealthState.UNAVAILABLE,
        reason_codes=("provider_unavailable",),
    )

    snapshot = engine.snapshot()
    assert snapshot.state is HealthState.UNAVAILABLE
    assert "provider_unavailable" in snapshot.reason_codes


def test_migration_required_aggregation_precedence() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="storage_migration",
        required=True,
        state=HealthState.MIGRATION_REQUIRED,
        reason_codes=("configuration_migration_required",),
    )
    engine.set_component(
        component="model_provider",
        required=True,
        state=HealthState.UNAVAILABLE,
        reason_codes=("provider_unavailable",),
    )

    snapshot = engine.snapshot()
    assert snapshot.state is HealthState.MIGRATION_REQUIRED
    assert "configuration_migration_required" in snapshot.reason_codes


def test_required_vs_optional_unavailable_behavior() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="optional_probe",
        required=False,
        state=HealthState.UNAVAILABLE,
        reason_codes=("dependency_unavailable",),
    )
    snapshot = engine.snapshot()
    assert snapshot.state is HealthState.DEGRADED

    engine.set_component(
        component="required_probe",
        required=True,
        state=HealthState.UNAVAILABLE,
        reason_codes=("dependency_unavailable",),
    )
    snapshot = engine.snapshot()
    assert snapshot.state is HealthState.UNAVAILABLE


def test_safe_reason_code_preservation_and_deduplication() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="probe_a",
        required=False,
        state=HealthState.DEGRADED,
        reason_codes=(
            HealthReasonCode.DEPENDENCY_UNAVAILABLE,
            "provider_unavailable",
            "provider_unavailable",
        ),
    )

    snapshot = engine.snapshot()
    assert snapshot.reason_codes.count("provider_unavailable") == 1
    assert "dependency_unavailable" in snapshot.reason_codes


def test_snapshot_structure_and_deterministic_ordering() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(component="zzz", required=False, state=HealthState.HEALTHY)
    engine.set_component(component="aaa", required=False, state=HealthState.HEALTHY)

    snapshot = engine.snapshot()
    names = tuple(component.component for component in snapshot.components)
    assert names == tuple(sorted(names))


def test_construction_from_configuration_and_capability_registry() -> None:
    manager, registry = _build_foundation()

    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )
    snapshot = engine.snapshot()

    assert any(component.component == "configuration_manager" for component in snapshot.components)
    assert any(component.component == "capability_registry" for component in snapshot.components)
    assert any(component.component == "integration_runtime" for component in snapshot.components)


def test_runtime_lifecycle_behavior_when_not_loaded() -> None:
    manager, registry = _build_foundation()

    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=False,
    )
    snapshot = engine.snapshot()

    assert snapshot.state is HealthState.UNAVAILABLE
    assert "service_not_loaded" in snapshot.reason_codes


def test_clear_behavior() -> None:
    manager, registry = _build_foundation()

    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )
    assert engine.snapshot().components

    engine.clear()
    snapshot = engine.snapshot()

    assert snapshot.state is HealthState.HEALTHY
    assert snapshot.components == ()


def test_no_unsafe_exception_message_leakage_from_configuration_errors() -> None:
    class _MigrationManager(VoiceIdentityConfigurationManager):
        @property
        def config(self):  # type: ignore[override]
            raise VoiceIdentityConfigMigrationRequiredError("secret path /mnt/private should not leak")

    manager = _MigrationManager()
    real_manager, registry = _build_foundation()
    _ = real_manager

    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )
    snapshot = engine.snapshot()

    assert snapshot.state is HealthState.MIGRATION_REQUIRED
    assert "configuration_migration_required" in snapshot.reason_codes
    assert all("private" not in reason for reason in snapshot.reason_codes)


def test_rejects_unsafe_reason_codes() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    with pytest.raises(VoiceIdentityUnsafeReasonCodeError):
        engine.set_component(
            component="unsafe_component",
            required=False,
            state=HealthState.DEGRADED,
            reason_codes=("raw exception: path /config/secrets",),
        )


def test_safe_details_are_preserved() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    engine.set_component(
        component="safe_probe",
        required=False,
        state=HealthState.DEGRADED,
        reason_codes=("dependency_unavailable",),
        details={
            "probe": "storage_v1",
            "attempt": 2,
            "retryable": True,
        },
    )

    snapshot = engine.snapshot()
    safe_probe = next(c for c in snapshot.components if c.component == "safe_probe")
    assert safe_probe.details["probe"] == "storage_v1"
    assert safe_probe.details["attempt"] == 2
    assert safe_probe.details["retryable"] is True


def test_rejects_unsafe_details() -> None:
    manager, registry = _build_foundation()
    engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=manager,
        capability_registry=registry,
        runtime_loaded=True,
    )

    with pytest.raises(VoiceIdentityUnsafeDetailsError):
        engine.set_component(
            component="unsafe_details_probe",
            required=False,
            state=HealthState.DEGRADED,
            reason_codes=("dependency_unavailable",),
            details={
                "error": "raw exception at /config/secrets/token.txt",
            },
        )