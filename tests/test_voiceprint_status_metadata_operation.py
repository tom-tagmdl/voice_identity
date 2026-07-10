from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass

import pytest

from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    VoiceprintRegistryHealth,
    VoiceprintRegistryValidationError,
    create_voiceprint_record,
)
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from custom_components.voice_identity.voiceprint_status_metadata_operation import (
    GetVoiceprintMetadataRequest,
    GetVoiceprintStatusFailureCategory,
    GetVoiceprintStatusOperation,
    GetVoiceprintStatusRequest,
)
from tests.test_voiceprint_registry import _FakeStorageProvider, _FakeStore


@dataclass
class _LifecycleHealth:
    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


@dataclass
class _RevisionHealth:
    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class _UnavailableRegistry:
    def list_records(self):
        raise VoiceprintRegistryValidationError("voiceprint_registry_not_loaded")

    async def validate_health(self):
        return VoiceprintRegistryHealth(
            state=HealthState.UNAVAILABLE,
            reason_codes=("voiceprint_registry_not_loaded",),
            details={"loaded": False},
        )


class _RaisingRevisionManager:
    def traverse_lineage(self, lineage_root_id):
        _ = lineage_root_id
        raise RuntimeError("Traceback secret path C:/voice/key")

    async def validate_health(self):
        return _RevisionHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True},
        )


class _SafeLifecycleManager:
    def __init__(self):
        self.activate_calls = 0
        self.deactivate_calls = 0
        self.delete_calls = 0
        self.supersede_calls = 0
        self.health_calls = 0

    async def activate_record(self, voiceprint_id):
        _ = voiceprint_id
        self.activate_calls += 1
        raise AssertionError("mutation not allowed")

    async def deactivate_record(self, voiceprint_id):
        _ = voiceprint_id
        self.deactivate_calls += 1
        raise AssertionError("mutation not allowed")

    async def delete_record(self, voiceprint_id):
        _ = voiceprint_id
        self.delete_calls += 1
        raise AssertionError("mutation not allowed")

    async def supersede_record(self, *, current_voiceprint_id, replacement_voiceprint_id):
        _ = current_voiceprint_id
        _ = replacement_voiceprint_id
        self.supersede_calls += 1
        raise AssertionError("mutation not allowed")

    async def validate_health(self):
        self.health_calls += 1
        return _LifecycleHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_lifecycle_ready",),
            details={"loaded": True},
        )


class _SafeRevisionManager:
    def __init__(self, *, revision_count: int):
        self.revision_count = revision_count
        self.traverse_calls = 0
        self.coordinate_calls = 0
        self.prepare_initial_calls = 0
        self.prepare_next_calls = 0
        self.health_calls = 0

    def traverse_lineage(self, lineage_root_id):
        _ = lineage_root_id
        self.traverse_calls += 1
        return tuple(object() for _ in range(self.revision_count))

    async def coordinate_supersession(self, *, current_voiceprint_id, replacement_voiceprint_id):
        _ = current_voiceprint_id
        _ = replacement_voiceprint_id
        self.coordinate_calls += 1
        raise AssertionError("mutation not allowed")

    def prepare_initial_record(self, **kwargs):
        _ = kwargs
        self.prepare_initial_calls += 1
        raise AssertionError("mutation not allowed")

    def prepare_next_revision_record(self, **kwargs):
        _ = kwargs
        self.prepare_next_calls += 1
        raise AssertionError("mutation not allowed")

    async def validate_health(self):
        self.health_calls += 1
        return _RevisionHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True},
        )


class _SafeRegistry:
    def __init__(self, *, record):
        self._record = record
        self.register_calls = 0
        self.update_calls = 0

    async def register_record(self, record):
        _ = record
        self.register_calls += 1
        raise AssertionError("mutation not allowed")

    async def update_record(self, record):
        _ = record
        self.update_calls += 1
        raise AssertionError("mutation not allowed")

    def list_records(self):
        return (self._record,)

    async def validate_health(self):
        return VoiceprintRegistryHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_registry_ready",),
            details={"loaded": True},
        )


async def _build_operation_with_record(
    *,
    lifecycle_state: VoiceprintLifecycleState = VoiceprintLifecycleState.ACTIVE,
    active: bool = True,
    include_revision_two: bool = False,
):
    storage = _FakeStorageProvider(existing_artifacts={"artifact_001", "artifact_002"})
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)

    root = create_voiceprint_record(
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
    await registry.register_record(root)

    if include_revision_two:
        child = create_voiceprint_record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            subject_id="person_001",
            revision=2,
            lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
            active=False,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
            lineage_root_id="vp_001",
            parent_voiceprint_id="vp_001",
            supersedes="vp_001",
        )
        await registry.register_record(child)

    operation = GetVoiceprintStatusOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )
    return operation


async def _build_components_with_record() -> tuple[VoiceprintRegistry, VoiceprintLifecycleManager, VoiceprintRevisionManager]:
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
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
    )
    await registry.register_record(record)
    return registry, lifecycle, revision


@pytest.mark.asyncio
async def test_successful_status_retrieval() -> None:
    operation = await _build_operation_with_record()
    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.voiceprint_id == "vp_001"
    assert result.lifecycle_status == "active"
    assert result.active is True
    assert result.revision == 1


@pytest.mark.asyncio
async def test_successful_metadata_retrieval() -> None:
    operation = await _build_operation_with_record()
    result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.voiceprint_id == "vp_001"
    assert result.metadata.model_identifier == "ecapa:v1"
    assert result.metadata.representation_version == 1


@pytest.mark.asyncio
async def test_voiceprint_not_found() -> None:
    operation = await _build_operation_with_record()
    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_missing"))

    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.VOICEPRINT_NOT_FOUND
    assert result.reason_code == "voiceprint_not_found"


@pytest.mark.asyncio
async def test_metadata_unavailable() -> None:
    lifecycle = _SafeLifecycleManager()
    revision = _SafeRevisionManager(revision_count=1)
    operation = GetVoiceprintStatusOperation.create(
        registry=_UnavailableRegistry(),
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )

    result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))
    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE
    assert result.reason_code == "metadata_unavailable"


@pytest.mark.asyncio
async def test_status_unavailable() -> None:
    lifecycle = _SafeLifecycleManager()
    revision = _SafeRevisionManager(revision_count=1)
    operation = GetVoiceprintStatusOperation.create(
        registry=_UnavailableRegistry(),
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )

    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))
    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.STATUS_UNAVAILABLE
    assert result.reason_code == "status_unavailable"


@pytest.mark.asyncio
async def test_unsupported_contract_version() -> None:
    operation = await _build_operation_with_record()
    result = await operation.execute(
        GetVoiceprintStatusRequest.create(voiceprint_id="vp_001", compatibility_version=2)
    )

    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.CONTRACT_VERSION_UNSUPPORTED
    assert result.reason_code == "contract_version_unsupported"


@pytest.mark.asyncio
async def test_operation_not_loaded() -> None:
    operation = await _build_operation_with_record()
    operation.clear()
    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.OPERATION_NOT_LOADED
    assert result.reason_code == "operation_not_loaded"


@pytest.mark.asyncio
async def test_internal_error_normalization() -> None:
    registry, lifecycle, _ = await _build_components_with_record()
    operation = GetVoiceprintStatusOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=_RaisingRevisionManager(),
    )

    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))
    assert result.success is False
    assert result.failure_category is GetVoiceprintStatusFailureCategory.OPERATION_INTERNAL_ERROR
    assert result.reason_code == "operation_internal_error"


@pytest.mark.asyncio
async def test_exception_text_not_exposed_in_diagnostics() -> None:
    registry, lifecycle, _ = await _build_components_with_record()
    operation = GetVoiceprintStatusOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=_RaisingRevisionManager(),
    )

    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))
    rendered = str(result)
    assert "Traceback" not in rendered
    assert "secret" not in rendered
    assert "key" not in rendered


@pytest.mark.asyncio
async def test_safe_diagnostics() -> None:
    operation = await _build_operation_with_record()
    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert "path" not in result.diagnostics
    assert "token" not in result.diagnostics


@pytest.mark.asyncio
async def test_metadata_projection_excludes_prohibited_fields() -> None:
    operation = await _build_operation_with_record()
    result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    payload = asdict(result.metadata)
    assert "encrypted_payload" not in payload
    assert "artifact_payload" not in payload
    assert "embedding" not in payload
    assert "storage_path" not in payload
    assert "key_reference" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lifecycle_state", "expected"),
    [
        (VoiceprintLifecycleState.PENDING, "pending"),
        (VoiceprintLifecycleState.ACTIVE, "active"),
        (VoiceprintLifecycleState.SUPERSEDED, "superseded"),
        (VoiceprintLifecycleState.DELETED, "retired"),
    ],
)
async def test_lifecycle_visibility_projection(lifecycle_state, expected) -> None:
    operation = await _build_operation_with_record(
        lifecycle_state=lifecycle_state,
        active=lifecycle_state is VoiceprintLifecycleState.ACTIVE,
    )
    result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.lifecycle_status == expected


@pytest.mark.asyncio
async def test_revision_visibility_projection() -> None:
    operation = await _build_operation_with_record(include_revision_two=True)
    result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.metadata.revision == 1
    assert result.metadata.revision_count == 2
    assert result.metadata.superseded is False


@pytest.mark.asyncio
async def test_version_compatibility_projection() -> None:
    operation = await _build_operation_with_record()
    result = await operation.get_metadata(
        GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001", compatibility_version=1)
    )

    assert result.success is True
    assert result.compatibility_version == 1
    assert result.metadata.compatibility_version == 1
    assert result.metadata.metadata_contract_version == 1


@pytest.mark.asyncio
async def test_registry_lifecycle_revision_consumption_without_mutation() -> None:
    record = create_voiceprint_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
    )
    registry = _SafeRegistry(record=record)
    lifecycle = _SafeLifecycleManager()
    revision = _SafeRevisionManager(revision_count=1)
    operation = GetVoiceprintStatusOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )

    status_result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))
    metadata_result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))
    health = await operation.validate_health()

    assert status_result.success is True
    assert metadata_result.success is True
    assert health.state is HealthState.HEALTHY
    assert registry.register_calls == 0
    assert registry.update_calls == 0
    assert lifecycle.activate_calls == 0
    assert lifecycle.deactivate_calls == 0
    assert lifecycle.delete_calls == 0
    assert lifecycle.supersede_calls == 0
    assert revision.coordinate_calls == 0
    assert revision.prepare_initial_calls == 0
    assert revision.prepare_next_calls == 0


@pytest.mark.asyncio
async def test_health_integration_ready_reason_code() -> None:
    operation = await _build_operation_with_record()
    health = await operation.validate_health()

    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("get_voiceprint_status_ready",)


@pytest.mark.asyncio
async def test_health_integration_not_loaded_reason_code() -> None:
    operation = await _build_operation_with_record()
    operation.clear()
    health = await operation.validate_health()

    assert health.state is HealthState.UNAVAILABLE
    assert health.reason_codes == ("operation_not_loaded",)


@pytest.mark.asyncio
async def test_privacy_boundary_enforcement() -> None:
    operation = await _build_operation_with_record()
    result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    rendered = str(result)
    assert "encrypted_payload" not in rendered
    assert "embedding" not in rendered
    assert "token" not in rendered


@pytest.mark.asyncio
async def test_concierge_consumer_compatibility_shape() -> None:
    operation = await _build_operation_with_record()
    status_result = await operation.execute(GetVoiceprintStatusRequest.create(voiceprint_id="vp_001"))
    metadata_result = await operation.get_metadata(GetVoiceprintMetadataRequest.create(voiceprint_id="vp_001"))

    assert status_result.success is True
    assert metadata_result.success is True

    status_payload = asdict(status_result)
    metadata_payload = asdict(metadata_result)

    assert status_payload["voiceprint_id"] == "vp_001"
    assert isinstance(status_payload["active"], bool)
    assert isinstance(status_payload["revision"], int)
    assert metadata_payload["metadata"]["lifecycle_state"] == "active"
    assert isinstance(metadata_payload["metadata"]["revision_count"], int)


@pytest.mark.asyncio
async def test_status_request_accepts_safe_metadata_and_correlation() -> None:
    operation = await _build_operation_with_record()
    request = GetVoiceprintStatusRequest.create(
        voiceprint_id="vp_001",
        correlation_id="corr_115",
        request_metadata={"source": "concierge", "token": "secret"},
    )

    result = await operation.execute(request)
    assert result.success is True


@pytest.mark.asyncio
async def test_metadata_request_accepts_safe_metadata_and_correlation() -> None:
    operation = await _build_operation_with_record()
    request = GetVoiceprintMetadataRequest.create(
        voiceprint_id="vp_001",
        correlation_id="corr_115",
        request_metadata={"source": "concierge", "path": "c:/tmp"},
    )

    result = await operation.get_metadata(request)
    assert result.success is True


def test_voiceprint_id_parse_from_repository_contract() -> None:
    parsed = VoiceprintId.parse("vp_001")
    assert parsed.value == "vp_001"
