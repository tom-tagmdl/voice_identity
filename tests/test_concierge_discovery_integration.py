from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from custom_components.voice_identity.capability_discovery_operation import (
    CompatibilityDiscoveryRequest,
    DiscoveryFailureResult,
    GetCapabilitiesFailureCategory,
    GetCapabilitiesOperation,
    GetCapabilitiesRequest,
    GetVersionDiscoveryRequest,
)
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.concierge_discovery_integration import (
    ConciergeDiscoveryFailureCategory,
    ConciergeDiscoveryIntegration,
    ConciergeDiscoveryRequest,
    ConciergeDiscoveryState,
    _CacheKey,
    _InMemoryCacheBackend,
)
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.health_state import HealthState


class _Entry:
    entry_id = "entry"
    data: dict[str, object] = {}
    options: dict[str, object] = {}


class _RaisingCache:
    def get(self, key, *, now):
        _ = key
        _ = now
        raise RuntimeError("cache failed")

    def set(self, key, projection, *, now):
        _ = key
        _ = projection
        _ = now
        raise RuntimeError("cache failed")

    def clear(self):
        raise RuntimeError("cache failed")


class _DegradedCapabilitiesOperation:
    def __init__(self, *, delegate: GetCapabilitiesOperation) -> None:
        self._delegate = delegate

    async def get_versions(self, request):
        return await self._delegate.get_versions(request)

    async def evaluate_compatibility(self, request):
        return await self._delegate.evaluate_compatibility(request)

    async def execute(self, request):
        return await self._delegate.execute(request)

    async def validate_health(self):
        health = await self._delegate.validate_health()
        return type(health)(
            state=HealthState.DEGRADED,
            reason_codes=("voice_identity_degraded",),
            details={"loaded": True},
        )


class _PartialCompatibilityCapabilitiesOperation:
    def __init__(self, *, delegate: GetCapabilitiesOperation) -> None:
        self._delegate = delegate

    async def get_versions(self, request):
        return await self._delegate.get_versions(request)

    async def evaluate_compatibility(self, request):
        _ = request
        return await self._delegate.evaluate_compatibility(
            CompatibilityDiscoveryRequest.create(
                requested_contract_version=1,
                requested_schema_version=99,
            )
        )

    async def execute(self, request):
        return await self._delegate.execute(request)

    async def validate_health(self):
        return await self._delegate.validate_health()


class _CompatibilityFailureCapabilitiesOperation:
    def __init__(self, *, delegate: GetCapabilitiesOperation) -> None:
        self._delegate = delegate

    async def get_versions(self, request):
        return await self._delegate.get_versions(request)

    async def evaluate_compatibility(self, request):
        return DiscoveryFailureResult(
            success=False,
            failure_category=GetCapabilitiesFailureCategory.OPERATION_INTERNAL_ERROR,
            reason_code="operation_internal_error",
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            diagnostics={"loaded": True},
            completed_at="2026-07-09T00:00:00+00:00",
        )

    async def execute(self, request):
        return await self._delegate.execute(request)

    async def validate_health(self):
        return await self._delegate.validate_health()


class _RecordingCapabilitiesOperation:
    def __init__(self, *, delegate: GetCapabilitiesOperation) -> None:
        self._delegate = delegate
        self.seen_get_versions = False
        self.seen_evaluate_compatibility = False
        self.seen_execute = False

    async def get_versions(self, request):
        self.seen_get_versions = isinstance(request, GetVersionDiscoveryRequest)
        return await self._delegate.get_versions(request)

    async def evaluate_compatibility(self, request):
        self.seen_evaluate_compatibility = isinstance(request, CompatibilityDiscoveryRequest)
        return await self._delegate.evaluate_compatibility(request)

    async def execute(self, request):
        self.seen_execute = isinstance(request, GetCapabilitiesRequest)
        return await self._delegate.execute(request)

    async def validate_health(self):
        return await self._delegate.validate_health()


class _RaisingCapabilitiesOperation:
    async def get_versions(self, request):
        _ = request
        raise RuntimeError("Traceback internal failure at C:/secret/path")

    async def evaluate_compatibility(self, request):
        _ = request
        raise RuntimeError("Traceback internal failure at C:/secret/path")

    async def execute(self, request):
        _ = request
        raise RuntimeError("Traceback internal failure at C:/secret/path")

    async def validate_health(self):
        return type("_Health", (), {
            "state": HealthState.UNAVAILABLE,
            "reason_codes": ("operation_internal_error",),
            "details": {"loaded": False},
        })()


def _build_capabilities_operation() -> GetCapabilitiesOperation:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry())
    registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)
    return GetCapabilitiesOperation.create(capability_registry=registry)


@pytest.mark.asyncio
async def test_voice_identity_discovered() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.service_available is True


@pytest.mark.asyncio
async def test_voice_identity_unavailable() -> None:
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=None)

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_UNAVAILABLE
    assert result.projection.discovery_state is ConciergeDiscoveryState.UNAVAILABLE


@pytest.mark.asyncio
async def test_voice_identity_incompatible_contract() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(
        ConciergeDiscoveryRequest.create(requested_contract_version=99),
    )

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE
    assert result.projection.discovery_state is ConciergeDiscoveryState.INCOMPATIBLE


@pytest.mark.asyncio
async def test_voice_identity_incompatible_schema() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(
        ConciergeDiscoveryRequest.create(requested_schema_version=99),
    )

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE


@pytest.mark.asyncio
async def test_voice_identity_degraded() -> None:
    degraded = _PartialCompatibilityCapabilitiesOperation(delegate=_build_capabilities_operation())
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=degraded)

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.discovery_state is ConciergeDiscoveryState.DEGRADED


@pytest.mark.asyncio
async def test_voice_identity_compatible() -> None:
    degraded_health = _DegradedCapabilitiesOperation(delegate=_build_capabilities_operation())
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=degraded_health)

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.discovery_state is ConciergeDiscoveryState.COMPATIBLE
    assert result.projection.service_compatible is True


@pytest.mark.asyncio
async def test_voice_identity_discovered_state() -> None:
    compatibility_failure = _CompatibilityFailureCapabilitiesOperation(
        delegate=_build_capabilities_operation(),
    )
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=compatibility_failure)

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.COMPATIBILITY_EVALUATION_FAILED
    assert result.projection.discovery_state is ConciergeDiscoveryState.DISCOVERED


@pytest.mark.asyncio
async def test_voice_identity_healthy() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.discovery_state is ConciergeDiscoveryState.HEALTHY
    assert result.projection.service_healthy is True


@pytest.mark.asyncio
async def test_capability_cache_creation_and_hit() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    first = await integration.discover(ConciergeDiscoveryRequest.create())
    second = await integration.discover(ConciergeDiscoveryRequest.create())

    assert first.success is True
    assert first.cache_hit is False
    assert second.success is True
    assert second.cache_hit is True


@pytest.mark.asyncio
async def test_capability_cache_refresh() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    _ = await integration.discover(ConciergeDiscoveryRequest.create())
    refreshed = await integration.discover(ConciergeDiscoveryRequest.create(force_refresh=True))

    assert refreshed.success is True
    assert refreshed.cache_hit is False


@pytest.mark.asyncio
async def test_cache_failure_handling() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
        cache_backend=_RaisingCache(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.CACHE_UNAVAILABLE


@pytest.mark.asyncio
async def test_capability_projection_handling() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert "generate_voiceprint" in result.projection.supported_capabilities
    assert "voiceprint_status" in result.projection.supported_capabilities
    assert "metadata_retrieval" in result.projection.supported_capabilities
    assert "delete_voiceprint" in result.projection.supported_capabilities
    assert "supersede_voiceprint" in result.projection.supported_capabilities
    assert "capability_discovery" in result.projection.supported_capabilities
    assert "version_discovery" in result.projection.supported_capabilities


@pytest.mark.asyncio
async def test_compatibility_validation_projection() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.compatibility.compatibility_status == "compatible"


@pytest.mark.asyncio
async def test_contract_and_schema_compatibility_projection() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    assert result.projection.compatibility.requested_contract_version == 1
    assert result.projection.compatibility.requested_schema_version == 1


@pytest.mark.asyncio
async def test_health_driven_state_changes() -> None:
    degraded = _DegradedCapabilitiesOperation(delegate=_build_capabilities_operation())
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=degraded)

    health = await integration.validate_health()

    assert health.state is HealthState.DEGRADED


@pytest.mark.asyncio
async def test_graceful_degradation_behavior() -> None:
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=None)

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.projection.service_available is False
    assert result.projection.enabled_capabilities == ()


@pytest.mark.asyncio
async def test_safe_failure_handling() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_RaisingCapabilitiesOperation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.OPERATION_INTERNAL_ERROR
    assert result.reason_code == "operation_internal_error"
    rendered = str(result)
    assert "Traceback" not in rendered
    assert "secret" not in rendered
    assert "path" not in rendered


@pytest.mark.asyncio
async def test_privacy_boundary_enforcement() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    payload = asdict(result)
    dumped = str(payload)
    assert "VoiceIdentityCapabilityRegistry" not in dumped
    assert "object at" not in dumped


@pytest.mark.asyncio
async def test_concierge_compatibility_projection_shape() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is True
    projection = result.projection
    assert isinstance(projection.supported_capabilities, tuple)
    assert isinstance(projection.enabled_capabilities, tuple)
    assert isinstance(projection.compatibility.compatibility_status, str)
    assert isinstance(projection.version_information.supported_contract_versions, tuple)
    assert isinstance(projection.version_information.supported_schema_versions, tuple)


@pytest.mark.asyncio
async def test_vi117_contract_consumption() -> None:
    recording = _RecordingCapabilitiesOperation(delegate=_build_capabilities_operation())
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=recording)

    result = await integration.discover(ConciergeDiscoveryRequest.create(force_refresh=True))

    assert result.success is True
    assert recording.seen_get_versions is True
    assert recording.seen_evaluate_compatibility is True
    assert recording.seen_execute is True


@pytest.mark.asyncio
async def test_operation_not_loaded() -> None:
    integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=_build_capabilities_operation(),
    )
    integration.clear()

    result = await integration.discover(ConciergeDiscoveryRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeDiscoveryFailureCategory.OPERATION_NOT_LOADED


@pytest.mark.asyncio
async def test_bounded_cache_eviction() -> None:
    integration = ConciergeDiscoveryIntegration.create(capabilities_operation=_build_capabilities_operation())
    discovery = await integration.discover(ConciergeDiscoveryRequest.create())
    assert discovery.success is True

    backend = _InMemoryCacheBackend(max_entries=1, ttl_seconds=120)
    now = datetime.now(timezone.utc)
    backend.set(_CacheKey(1, 1), discovery.projection, now=now)
    backend.set(_CacheKey(1, 2), discovery.projection, now=now)

    assert backend.get(_CacheKey(1, 1), now=now) is None
    assert backend.get(_CacheKey(1, 2), now=now) is not None
