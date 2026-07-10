from __future__ import annotations

import pytest

from custom_components.voice_identity.capability_registry import (
    CapabilityCategory,
    CapabilityDescriptor,
    CapabilityMaturity,
    VoiceIdentityCapabilityDuplicateError,
    VoiceIdentityCapabilityRegistry,
)
from custom_components.voice_identity.configuration import (
    AttributionConfiguration,
    CleanupConfiguration,
    DiagnosticsConfiguration,
    FeatureFlagsConfiguration,
    GenerationConfiguration,
    ServiceConfiguration,
    StorageConfiguration,
    VoiceIdentityConfiguration,
    VoiceIdentityConfigurationManager,
)


def _build_config(
    *,
    service_enabled: bool = True,
    diagnostics_enabled: bool = True,
    enable_repairs: bool = True,
    enable_runtime_attribution: bool = False,
    config_schema_version: int = 1,
) -> VoiceIdentityConfiguration:
    return VoiceIdentityConfiguration(
        config_schema_version=config_schema_version,
        service=ServiceConfiguration(
            enabled=service_enabled,
            startup_timeout_seconds=30,
            max_cached_voiceprints=2500,
        ),
        storage=StorageConfiguration(
            provider="local_filesystem",
            base_path="voice_identity",
            encryption_required=True,
        ),
        generation=GenerationConfiguration(
            model_preference="ecapa_v1",
            min_sample_count=6,
            max_sample_count=12,
            quality_threshold=0.75,
            supported_models=("ecapa_v1",),
        ),
        cleanup=CleanupConfiguration(
            enabled=True,
            session_timeout_seconds=900,
            reconcile_on_startup=True,
        ),
        diagnostics=DiagnosticsConfiguration(
            enabled=diagnostics_enabled,
            allowlist_only=True,
            include_runtime_metrics=True,
        ),
        feature_flags=FeatureFlagsConfiguration(
            enable_runtime_attribution=enable_runtime_attribution,
            enable_repairs=enable_repairs,
            enable_experimental_models=False,
        ),
        attribution=AttributionConfiguration(
            default_confidence_threshold=0.7,
            max_candidate_scope_size=25,
            require_attribution_for_identity_context=False,
        ),
    )


def test_default_registration_and_lookup() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config())
    registry.register_defaults()

    assert registry.supports("voiceprint_generation") is True
    assert registry.supports("runtime_attribution") is True
    assert registry.supports("diagnostics") is True
    assert registry.supports("concierge_enrollment") is True

    diagnostics = registry.status("diagnostics")
    assert diagnostics is not None
    assert diagnostics.supported is True
    assert diagnostics.enabled is False

    health_service = registry.status("health_service")
    assert health_service is not None
    assert health_service.supported is True
    assert health_service.enabled is True


def test_unknown_capability_returns_false_and_none_status() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config())
    registry.register_defaults()

    assert registry.supports("missing_capability") is False
    assert registry.status("missing_capability") is None


def test_duplicate_registration_raises_error() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config())
    descriptor = CapabilityDescriptor(
        name="test_capability",
        description="capability for duplicate test",
        category=CapabilityCategory.FOUNDATION,
        maturity=CapabilityMaturity.IMPLEMENTED,
    )

    registry.register(descriptor)
    with pytest.raises(VoiceIdentityCapabilityDuplicateError):
        registry.register(descriptor)


def test_version_aware_behavior_for_future_capability() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config(config_schema_version=1))
    descriptor = CapabilityDescriptor(
        name="future_capability",
        description="becomes supported in schema v2",
        category=CapabilityCategory.OPERATIONS,
        maturity=CapabilityMaturity.PLANNED,
        introduced_config_schema_version=2,
    )
    registry.register(descriptor)

    assert registry.supports("future_capability") is False
    assert registry.supports("future_capability", config_schema_version=2) is True


def test_registry_lifecycle_update_configuration_changes_enablement() -> None:
    registry = VoiceIdentityCapabilityRegistry(
        _build_config(service_enabled=True),
    )
    registry.register_defaults()

    before = registry.status("configuration_manager")
    assert before is not None
    assert before.enabled is True

    registry.update_configuration(_build_config(service_enabled=False))

    after = registry.status("configuration_manager")
    assert after is not None
    assert after.enabled is False


def test_registry_lifecycle_clear_removes_registered_capabilities() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config())
    registry.register_defaults()
    assert registry.supports("capability_registry") is True

    registry.clear()

    assert registry.supports("capability_registry") is False
    assert registry.list_capabilities() == ()


def test_snapshot_contains_versions_and_sorted_payload() -> None:
    registry = VoiceIdentityCapabilityRegistry(_build_config())
    registry.register_defaults()

    snapshot = registry.snapshot()

    assert snapshot.registry_schema_version == 1
    assert snapshot.config_schema_version == 1
    assert len(snapshot.capabilities) > 0
    names = tuple(item.descriptor.name for item in snapshot.capabilities)
    assert names == tuple(sorted(names))


def test_from_configuration_manager_consumes_authoritative_config() -> None:
    manager = VoiceIdentityConfigurationManager()

    class _Entry:
        entry_id = "entry"
        data = {"feature_flags": {"enable_runtime_attribution": True}}
        options: dict[str, object] = {}

    manager.load_from_entry(_Entry())

    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)

    assert registry.supports("runtime_attribution") is True
    status = registry.status("runtime_attribution")
    assert status is not None
    assert status.enabled is False