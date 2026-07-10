from __future__ import annotations

from dataclasses import asdict

import pytest

from custom_components.voice_identity.concierge_discovery_integration import (
    ConciergeCompatibilityProjection,
    ConciergeDiscoveryFailureCategory,
    ConciergeDiscoveryFailureResult,
    ConciergeDiscoveryProjection,
    ConciergeDiscoveryState,
    ConciergeDiscoverySuccessResult,
    ConciergeVersionInformation,
)
from custom_components.voice_identity.concierge_voiceprofile_metadata_integration import (
    ConciergeVoiceProfileFailureCategory,
    ConciergeVoiceProfileMetadataIntegration,
    ConciergeVoiceProfileReadiness,
    ConciergeVoiceProfileRequest,
    ConciergeVoiceProfileState,
    _CacheKey,
    _InMemoryCacheBackend,
)
from custom_components.voice_identity.voiceprint_status_metadata_operation import (
    GetVoiceprintMetadataSuccessResult,
    GetVoiceprintOperationFailureResult,
    GetVoiceprintStatusFailureCategory,
    GetVoiceprintStatusOperation,
    VoiceprintPublicMetadata,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    create_voiceprint_record,
)
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_voiceprint_registry import _FakeStorageProvider, _FakeStore


class _StaticDiscoveryIntegration:
    def __init__(self, *, result) -> None:
        self._result = result
        self.calls = 0

    async def discover(self, request):
        _ = request
        self.calls += 1
        return self._result


class _RaisingDiscoveryIntegration:
    async def discover(self, request):
        _ = request
        raise RuntimeError("Traceback internal failure at C:/secret/path")


class _FailureStatusOperation:
    def __init__(self, *, failure_category: GetVoiceprintStatusFailureCategory) -> None:
        self._failure_category = failure_category

    async def get_metadata(self, request):
        return GetVoiceprintOperationFailureResult(
            success=False,
            voiceprint_id=request.voiceprint_id,
            failure_category=self._failure_category,
            reason_code=self._failure_category.value,
            compatibility_version=request.compatibility_version,
            diagnostics={"loaded": True},
            completed_at="2026-07-09T00:00:00+00:00",
        )


class _RaisingGetCache:
    def get(self, key, *, now):
        _ = key
        _ = now
        raise RuntimeError("cache get failed")

    def set(self, key, projection, *, now):
        _ = key
        _ = projection
        _ = now

    def clear(self):
        return None


class _RaisingSetCache:
    def get(self, key, *, now):
        _ = key
        _ = now
        return None

    def set(self, key, projection, *, now):
        _ = key
        _ = projection
        _ = now
        raise RuntimeError("cache set failed")

    def clear(self):
        return None


class _RecordingDiscoveryIntegration:
    def __init__(self, *, results: list) -> None:
        self._results = list(results)
        self.requests = []

    async def discover(self, request):
        self.requests.append(request)
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


class _RecordingStatusOperation:
    def __init__(self, *, metadata_result) -> None:
        self.metadata_result = metadata_result
        self.requests = []

    async def get_metadata(self, request):
        self.requests.append(request)
        return self.metadata_result


def _metadata_success_result(*, voiceprint_id: str = "vp_001") -> GetVoiceprintMetadataSuccessResult:
    return GetVoiceprintMetadataSuccessResult(
        success=True,
        voiceprint_id=voiceprint_id,
        compatibility_version=1,
        metadata=VoiceprintPublicMetadata(
            metadata_contract_version=1,
            compatibility_version=1,
            voiceprint_id=voiceprint_id,
            lifecycle_state="active",
            active=True,
            revision=1,
            revision_count=1,
            superseded=False,
            created_timestamp="2026-07-09T00:00:00+00:00",
            updated_timestamp="2026-07-09T00:00:00+00:00",
            provider_identifier="voice_identity",
            model_identifier="ecapa:v1",
            representation_version=1,
            quality_summary="quality_summary_unavailable",
            status_summary="voiceprint_active",
        ),
        diagnostics={"loaded": True},
    )


def _version_information() -> ConciergeVersionInformation:
    return ConciergeVersionInformation(
        service_name="voice_identity",
        service_version="0.1.0",
        discovery_contract_version=1,
        metadata_schema_version=1,
        capability_discovery_schema_version=1,
        status_contract_version=1,
        supported_contract_versions=(1,),
        supported_schema_versions=(1,),
    )


def _discovery_projection(
    *,
    state: ConciergeDiscoveryState = ConciergeDiscoveryState.HEALTHY,
    service_available: bool = True,
    supported_capabilities: tuple[str, ...] = ("voiceprint_status", "metadata_retrieval"),
    enabled_capabilities: tuple[str, ...] = ("voiceprint_status", "metadata_retrieval"),
) -> ConciergeDiscoveryProjection:
    return ConciergeDiscoveryProjection(
        discovery_state=state,
        service_available=service_available,
        service_healthy=state is ConciergeDiscoveryState.HEALTHY,
        service_compatible=state is not ConciergeDiscoveryState.INCOMPATIBLE,
        supported_capabilities=supported_capabilities,
        enabled_capabilities=enabled_capabilities,
        compatibility=ConciergeCompatibilityProjection(
            compatibility_status="compatible",
            upgrade_guidance="none",
            requested_contract_version=1,
            requested_schema_version=1,
            supported_contract_versions=(1,),
            supported_schema_versions=(1,),
        ),
        version_information=_version_information(),
    )


def _discovery_success(
    *,
    state: ConciergeDiscoveryState = ConciergeDiscoveryState.HEALTHY,
    service_available: bool = True,
    supported_capabilities: tuple[str, ...] = ("voiceprint_status", "metadata_retrieval"),
    enabled_capabilities: tuple[str, ...] = ("voiceprint_status", "metadata_retrieval"),
):
    return ConciergeDiscoverySuccessResult(
        success=True,
        projection=_discovery_projection(
            state=state,
            service_available=service_available,
            supported_capabilities=supported_capabilities,
            enabled_capabilities=enabled_capabilities,
        ),
        cache_hit=False,
        diagnostics={"loaded": True},
    )


async def _build_status_operation_with_record(
    *,
    lifecycle_state: VoiceprintLifecycleState,
    active: bool,
) -> GetVoiceprintStatusOperation:
    storage = _FakeStorageProvider(existing_artifacts={"artifact_001"})
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)

    record = create_voiceprint_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        revision=1,
        lifecycle_state=lifecycle_state,
        active=active,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
    )
    await registry.register_record(record)
    return GetVoiceprintStatusOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )


@pytest.mark.asyncio
async def test_voiceprofile_active_ready_projection() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    )
    discovery = _StaticDiscoveryIntegration(result=_discovery_success())
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.projection.state is ConciergeVoiceProfileState.ACTIVE
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.READY
    assert result.projection.profile_ready is True


@pytest.mark.asyncio
async def test_voiceprofile_superseded_requires_enrollment() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
        active=False,
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.projection.state is ConciergeVoiceProfileState.SUPERSEDED
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.ENROLLMENT_REQUIRED


@pytest.mark.asyncio
async def test_voiceprofile_retired_requires_enrollment() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.DELETED,
        active=False,
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.projection.state is ConciergeVoiceProfileState.RETIRED
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.ENROLLMENT_REQUIRED


@pytest.mark.asyncio
async def test_voiceprofile_unknown_state_projection() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.FAILED,
        active=False,
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.projection.state is ConciergeVoiceProfileState.UNKNOWN
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.UNKNOWN


@pytest.mark.asyncio
async def test_voiceprofile_enrollment_required_when_missing_id() -> None:
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create())

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.ENROLLMENT_REQUIRED
    assert result.projection.state is ConciergeVoiceProfileState.NOT_ENROLLED


@pytest.mark.asyncio
async def test_voiceprofile_not_found_failure_mapping() -> None:
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.VOICEPRINT_NOT_FOUND
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_missing"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.VOICE_PROFILE_NOT_FOUND


@pytest.mark.asyncio
async def test_voiceprofile_metadata_unavailable_failure_mapping() -> None:
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.METADATA_UNAVAILABLE


@pytest.mark.asyncio
async def test_voiceprofile_unavailable_when_discovery_unavailable() -> None:
    discovery_result = ConciergeDiscoveryFailureResult(
        success=False,
        failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
        reason_code="voice_identity_unavailable",
        projection=_discovery_projection(state=ConciergeDiscoveryState.UNAVAILABLE, service_available=False),
        diagnostics={"loaded": True},
        completed_at="2026-07-09T00:00:00+00:00",
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=discovery_result),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_UNAVAILABLE
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.UNAVAILABLE


@pytest.mark.asyncio
async def test_voiceprofile_incompatible_when_discovery_reports_incompatible_failure() -> None:
    discovery_result = ConciergeDiscoveryFailureResult(
        success=False,
        failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
        reason_code="voice_identity_incompatible",
        projection=_discovery_projection(state=ConciergeDiscoveryState.INCOMPATIBLE),
        diagnostics={"loaded": True},
        completed_at="2026-07-09T00:00:00+00:00",
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=discovery_result),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_INCOMPATIBLE
    assert result.projection.readiness is ConciergeVoiceProfileReadiness.INCOMPATIBLE


@pytest.mark.asyncio
async def test_voiceprofile_operation_not_loaded() -> None:
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=None,
        discovery_integration=None,
    )
    integration.clear()

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.OPERATION_NOT_LOADED


@pytest.mark.asyncio
async def test_voiceprofile_cache_hit_and_force_refresh() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    )
    discovery = _StaticDiscoveryIntegration(result=_discovery_success())
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    first = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))
    second = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))
    refreshed = await integration.resolve(
        ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001", force_refresh=True)
    )

    assert first.success is True
    assert first.cache_hit is False
    assert second.success is True
    assert second.cache_hit is True
    assert refreshed.success is True
    assert refreshed.cache_hit is False
    assert discovery.calls >= 2


@pytest.mark.asyncio
async def test_cache_backend_get_failure_falls_back_safely() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
        cache_backend=_RaisingGetCache(),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.cache_hit is False


@pytest.mark.asyncio
async def test_cache_backend_set_failure_degrades_safely() -> None:
    status_operation = await _build_status_operation_with_record(
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
        cache_backend=_RaisingSetCache(),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.cache_hit is False
    assert result.diagnostics["cache"] == "unavailable"


@pytest.mark.asyncio
async def test_cache_bounded_eviction_behavior() -> None:
    backend = _InMemoryCacheBackend(max_entries=1, ttl_seconds=120)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    projection = _discovery_projection()
    # Use minimal projection-shaped placeholders for cache storage behavior.
    cache_projection = __import__(
        "custom_components.voice_identity.concierge_voiceprofile_metadata_integration",
        fromlist=["ConciergeVoiceProfileProjection"],
    ).ConciergeVoiceProfileProjection(
        voiceprint_id="vp_001",
        active=True,
        lifecycle_state="active",
        enrollment_state="complete",
        version_information=__import__(
            "custom_components.voice_identity.concierge_voiceprofile_metadata_integration",
            fromlist=["ConciergeVoiceProfileVersionInformation"],
        ).ConciergeVoiceProfileVersionInformation(
            service_name="voice_identity",
            service_version="0.1.0",
            discovery_contract_version=1,
            metadata_schema_version=1,
            capability_discovery_schema_version=1,
            status_contract_version=1,
            supported_contract_versions=(1,),
            supported_schema_versions=(1,),
        ),
        profile_ready=True,
        superseded=False,
        created_timestamp="2026-07-09T00:00:00+00:00",
        updated_timestamp="2026-07-09T00:00:00+00:00",
        state=ConciergeVoiceProfileState.ACTIVE,
        readiness=ConciergeVoiceProfileReadiness.READY,
    )
    backend.set(
        _CacheKey("vp_001", 1, 1, 1, ConciergeDiscoveryState.HEALTHY.value, True, True),
        cache_projection,
        now=now,
    )
    backend.set(
        _CacheKey("vp_002", 1, 1, 1, ConciergeDiscoveryState.HEALTHY.value, True, True),
        cache_projection,
        now=now,
    )

    assert (
        backend.get(
            _CacheKey("vp_001", 1, 1, 1, ConciergeDiscoveryState.HEALTHY.value, True, True),
            now=now,
        )
        is None
    )
    assert (
        backend.get(
            _CacheKey("vp_002", 1, 1, 1, ConciergeDiscoveryState.HEALTHY.value, True, True),
            now=now,
        )
        is not None
    )


@pytest.mark.asyncio
async def test_cache_stale_entry_handling() -> None:
    backend = _InMemoryCacheBackend(max_entries=2, ttl_seconds=1)
    datetime_mod = __import__("datetime")
    now = datetime_mod.datetime.now(datetime_mod.timezone.utc)
    stale_now = now - datetime_mod.timedelta(seconds=2)
    cache_projection = __import__(
        "custom_components.voice_identity.concierge_voiceprofile_metadata_integration",
        fromlist=["ConciergeVoiceProfileProjection"],
    ).ConciergeVoiceProfileProjection(
        voiceprint_id="vp_001",
        active=True,
        lifecycle_state="active",
        enrollment_state="complete",
        version_information=__import__(
            "custom_components.voice_identity.concierge_voiceprofile_metadata_integration",
            fromlist=["ConciergeVoiceProfileVersionInformation"],
        ).ConciergeVoiceProfileVersionInformation(
            service_name="voice_identity",
            service_version="0.1.0",
            discovery_contract_version=1,
            metadata_schema_version=1,
            capability_discovery_schema_version=1,
            status_contract_version=1,
            supported_contract_versions=(1,),
            supported_schema_versions=(1,),
        ),
        profile_ready=True,
        superseded=False,
        created_timestamp="2026-07-09T00:00:00+00:00",
        updated_timestamp="2026-07-09T00:00:00+00:00",
        state=ConciergeVoiceProfileState.ACTIVE,
        readiness=ConciergeVoiceProfileReadiness.READY,
    )
    key = _CacheKey("vp_001", 1, 1, 1, ConciergeDiscoveryState.HEALTHY.value, True, True)
    backend.set(key, cache_projection, now=stale_now)

    assert backend.get(key, now=now) is None


@pytest.mark.asyncio
async def test_discovery_unavailable_after_cache_creation_invalidates_ready_state() -> None:
    status_operation = _RecordingStatusOperation(metadata_result=_metadata_success_result())
    discovery = _RecordingDiscoveryIntegration(
        results=[
            _discovery_success(state=ConciergeDiscoveryState.HEALTHY, service_available=True),
            ConciergeDiscoveryFailureResult(
                success=False,
                failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_discovery_projection(
                    state=ConciergeDiscoveryState.UNAVAILABLE,
                    service_available=False,
                ),
                diagnostics={"loaded": True},
                completed_at="2026-07-09T00:00:00+00:00",
            ),
        ]
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    first = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))
    second = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert first.success is True
    assert first.projection.readiness is ConciergeVoiceProfileReadiness.READY
    assert second.success is False
    assert second.failure_category is ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_compatibility_change_after_cache_creation_invalidates_ready_state() -> None:
    status_operation = _RecordingStatusOperation(metadata_result=_metadata_success_result())
    discovery = _RecordingDiscoveryIntegration(
        results=[
            _discovery_success(state=ConciergeDiscoveryState.HEALTHY, service_available=True),
            ConciergeDiscoveryFailureResult(
                success=False,
                failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
                reason_code="voice_identity_incompatible",
                projection=_discovery_projection(state=ConciergeDiscoveryState.INCOMPATIBLE),
                diagnostics={"loaded": True},
                completed_at="2026-07-09T00:00:00+00:00",
            ),
        ]
    )
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    first = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))
    second = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert first.success is True
    assert first.projection.readiness is ConciergeVoiceProfileReadiness.READY
    assert second.success is False
    assert second.failure_category is ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_INCOMPATIBLE


@pytest.mark.asyncio
async def test_explicit_vi118_discovery_request_contract_construction() -> None:
    discovery = _RecordingDiscoveryIntegration(results=[_discovery_success()])
    status_operation = _RecordingStatusOperation(metadata_result=_metadata_success_result())
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    request = ConciergeVoiceProfileRequest.create(
        voiceprint_id="vp_001",
        requested_discovery_contract_version=2,
        requested_discovery_schema_version=3,
        metadata_contract_version=4,
        force_refresh=True,
        correlation_id="Corr-01",
        request_metadata={"safe_key": "Safe-Value", "secret": "hidden"},
    )
    result = await integration.resolve(request)

    assert result.success is True
    assert len(discovery.requests) == 1
    discover_request = discovery.requests[0]
    assert discover_request.requested_contract_version == 2
    assert discover_request.requested_schema_version == 3
    assert discover_request.force_refresh is True
    assert discover_request.correlation_id == "corr-01"
    assert discover_request.request_metadata.get("safe_key") == "safe-value"
    assert "secret" not in discover_request.request_metadata


@pytest.mark.asyncio
async def test_explicit_vi115_metadata_request_contract_construction() -> None:
    discovery = _RecordingDiscoveryIntegration(results=[_discovery_success()])
    status_operation = _RecordingStatusOperation(metadata_result=_metadata_success_result())
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=status_operation,
        discovery_integration=discovery,
    )

    request = ConciergeVoiceProfileRequest.create(
        voiceprint_id="vp_abc",
        metadata_contract_version=7,
        correlation_id="Meta-02",
        request_metadata={"safe_key": "Meta-Value", "token": "hidden"},
    )
    result = await integration.resolve(request)

    assert result.success is True
    assert len(status_operation.requests) == 1
    metadata_request = status_operation.requests[0]
    assert metadata_request.voiceprint_id == "vp_abc"
    assert metadata_request.compatibility_version == 7
    assert metadata_request.correlation_id == "meta-02"
    assert metadata_request.request_metadata.get("safe_key") == "meta-value"
    assert "token" not in metadata_request.request_metadata


@pytest.mark.asyncio
async def test_safe_failure_handling_internal_errors() -> None:
    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=None,
        discovery_integration=_RaisingDiscoveryIntegration(),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is ConciergeVoiceProfileFailureCategory.OPERATION_INTERNAL_ERROR
    rendered = str(result)
    assert "Traceback" not in rendered
    assert "secret" not in rendered
    assert "path" not in rendered


@pytest.mark.asyncio
async def test_privacy_boundary_enforcement() -> None:
    metadata = VoiceprintPublicMetadata(
        metadata_contract_version=1,
        compatibility_version=1,
        voiceprint_id="vp_001",
        lifecycle_state="active",
        active=True,
        revision=1,
        revision_count=1,
        superseded=False,
        created_timestamp="2026-07-09T00:00:00+00:00",
        updated_timestamp="2026-07-09T00:00:00+00:00",
        provider_identifier="voice_identity",
        model_identifier="ecapa:v1",
        representation_version=1,
        quality_summary="quality_summary_unavailable",
        status_summary="voiceprint_active",
    )
    status_operation = _FailureStatusOperation(
        failure_category=GetVoiceprintStatusFailureCategory.OPERATION_INTERNAL_ERROR
    )

    class _StaticSuccessStatusOperation:
        async def get_metadata(self, request):
            return GetVoiceprintMetadataSuccessResult(
                success=True,
                voiceprint_id=request.voiceprint_id,
                compatibility_version=request.compatibility_version,
                metadata=metadata,
                diagnostics={"loaded": True},
            )

    integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_StaticSuccessStatusOperation(),
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )

    result = await integration.resolve(ConciergeVoiceProfileRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    payload = asdict(result)
    dumped = str(payload)
    assert "object at" not in dumped
    assert "VoiceprintRegistry" not in dumped


@pytest.mark.asyncio
async def test_health_projection_states() -> None:
    healthy = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(result=_discovery_success()),
    )
    unhealthy = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=_FailureStatusOperation(
            failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
        ),
        discovery_integration=_StaticDiscoveryIntegration(
            result=ConciergeDiscoveryFailureResult(
                success=False,
                failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_discovery_projection(
                    state=ConciergeDiscoveryState.UNAVAILABLE,
                    service_available=False,
                ),
                diagnostics={"loaded": True},
                completed_at="2026-07-09T00:00:00+00:00",
            )
        ),
    )

    healthy_health = await healthy.validate_health()
    unhealthy_health = await unhealthy.validate_health()

    assert healthy_health.state is HealthState.HEALTHY
    assert unhealthy_health.state is HealthState.UNAVAILABLE
