from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass

import pytest

from custom_components.voice_identity.delete_supersede_voiceprint_operation import (
    DeleteSupersedeFailureCategory,
    DeleteSupersedeVoiceprintOperation,
    DeleteVoiceprintRequest,
    SupersedeVoiceprintRequest,
    VoiceprintOperationStatus,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    create_voiceprint_record,
)
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_voiceprint_registry import _FakeStorageProvider, _FakeStore


@dataclass
class _Health:
    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class _RaisingRevisionManager:
    def __init__(self) -> None:
        self.called = False

    async def coordinate_supersession(self, *, current_voiceprint_id, replacement_voiceprint_id):
        _ = current_voiceprint_id
        _ = replacement_voiceprint_id
        self.called = True
        raise RuntimeError("Traceback internal failure at C:/secret/path")

    async def validate_health(self):
        return _Health(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True},
        )


class _RaisingLifecycleManager:
    async def delete_record(self, voiceprint_id):
        _ = voiceprint_id
        raise RuntimeError("Traceback internal delete at C:/secret/path")

    async def validate_health(self):
        return _Health(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_lifecycle_ready",),
            details={"loaded": True},
        )


class _GuardRegistry:
    def __init__(self, *, records):
        self._records = records
        self.update_calls = 0
        self.register_calls = 0

    def list_records(self):
        return self._records

    async def validate_health(self):
        return _Health(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_registry_ready",),
            details={"loaded": True},
        )

    async def update_record(self, record):
        _ = record
        self.update_calls += 1
        raise AssertionError("operation must not update registry directly")

    async def register_record(self, record):
        _ = record
        self.register_calls += 1
        raise AssertionError("operation must not register records directly")


class _GuardLifecycleManager:
    def __init__(self, *, deleted_record):
        self.deleted_record = deleted_record
        self.delete_calls = 0
        self.activate_calls = 0
        self.supersede_calls = 0

    async def delete_record(self, voiceprint_id):
        _ = voiceprint_id
        self.delete_calls += 1
        return self.deleted_record

    async def activate_record(self, voiceprint_id):
        _ = voiceprint_id
        self.activate_calls += 1
        raise AssertionError("not used")

    async def supersede_record(self, *, current_voiceprint_id, replacement_voiceprint_id):
        _ = current_voiceprint_id
        _ = replacement_voiceprint_id
        self.supersede_calls += 1
        raise AssertionError("not used")

    async def validate_health(self):
        return _Health(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_lifecycle_ready",),
            details={"loaded": True},
        )


class _GuardRevisionManager:
    def __init__(self, *, previous_record, active_record):
        self.previous_record = previous_record
        self.active_record = active_record
        self.coordinate_calls = 0
        self.prepare_calls = 0

    async def coordinate_supersession(self, *, current_voiceprint_id, replacement_voiceprint_id):
        _ = current_voiceprint_id
        _ = replacement_voiceprint_id
        self.coordinate_calls += 1
        return self.previous_record, self.active_record

    def prepare_initial_record(self, **kwargs):
        _ = kwargs
        self.prepare_calls += 1
        raise AssertionError("not used")

    def prepare_next_revision_record(self, **kwargs):
        _ = kwargs
        self.prepare_calls += 1
        raise AssertionError("not used")

    async def validate_health(self):
        return _Health(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True},
        )


async def _build_operation(
    *,
    include_replacement: bool = False,
    existing_state: VoiceprintLifecycleState = VoiceprintLifecycleState.ACTIVE,
    existing_active: bool = True,
    replacement_state: VoiceprintLifecycleState = VoiceprintLifecycleState.PENDING,
    replacement_revision: int = 2,
):
    existing_artifacts = {"artifact_001", "artifact_002"}
    storage = _FakeStorageProvider(existing_artifacts=existing_artifacts)
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)

    current = create_voiceprint_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        revision=1,
        lifecycle_state=existing_state,
        active=existing_active,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
    )
    await registry.register_record(current)

    if include_replacement:
        replacement = create_voiceprint_record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            subject_id="person_001",
            revision=replacement_revision,
            lifecycle_state=replacement_state,
            active=False,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
            lineage_root_id="vp_001",
            parent_voiceprint_id="vp_001",
            supersedes="vp_001",
        )
        await registry.register_record(replacement)

    operation = DeleteSupersedeVoiceprintOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )
    return operation, registry


@pytest.mark.asyncio
async def test_successful_deletion() -> None:
    operation, registry = await _build_operation()

    result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_001"))

    assert result.success is True
    assert result.operation_status is VoiceprintOperationStatus.COMPLETED
    assert result.lifecycle_status == "deleted"

    record = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    assert record.lifecycle_state is VoiceprintLifecycleState.DELETED
    assert record.active is False


@pytest.mark.asyncio
async def test_successful_supersede() -> None:
    operation, registry = await _build_operation(include_replacement=True)

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_002",
        )
    )

    assert result.success is True
    assert result.status is VoiceprintOperationStatus.COMPLETED
    assert result.previous_voiceprint_id == "vp_001"
    assert result.active_voiceprint_id == "vp_002"

    previous = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    active = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_002"))
    assert previous.lifecycle_state is VoiceprintLifecycleState.SUPERSEDED
    assert previous.active is False
    assert previous.lineage.superseded_by == VoiceprintId.parse("vp_002")
    assert active.lifecycle_state is VoiceprintLifecycleState.ACTIVE
    assert active.active is True


@pytest.mark.asyncio
async def test_voiceprint_not_found() -> None:
    operation, _ = await _build_operation()

    result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_missing"))

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.VOICEPRINT_NOT_FOUND
    assert result.reason_code == "voiceprint_not_found"


@pytest.mark.asyncio
async def test_invalid_supersede() -> None:
    operation, _ = await _build_operation(include_replacement=True)

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_001",
        )
    )

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.SUPERSEDE_INVALID
    assert result.reason_code == "supersede_invalid"


@pytest.mark.asyncio
async def test_supersede_of_inactive_voiceprint() -> None:
    operation, _ = await _build_operation(
        include_replacement=True,
        existing_state=VoiceprintLifecycleState.INACTIVE,
        existing_active=False,
    )

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_002",
        )
    )

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.VOICEPRINT_NOT_ACTIVE
    assert result.reason_code == "voiceprint_not_active"


@pytest.mark.asyncio
async def test_lifecycle_transition_failure() -> None:
    operation, _ = await _build_operation(
        existing_state=VoiceprintLifecycleState.PENDING,
        existing_active=False,
    )

    result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_001"))

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.LIFECYCLE_TRANSITION_INVALID
    assert result.reason_code == "lifecycle_transition_invalid"


@pytest.mark.asyncio
async def test_revision_conflict_handling() -> None:
    operation, _ = await _build_operation(
        include_replacement=True,
        replacement_revision=3,
    )

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_002",
        )
    )

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.REVISION_CONFLICT
    assert result.reason_code == "revision_conflict"


@pytest.mark.asyncio
async def test_registry_consistency_preservation() -> None:
    operation, registry = await _build_operation(include_replacement=True)

    _ = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_002",
        )
    )

    records = registry.list_records()
    assert len(records) == 2
    assert tuple(record.voiceprint_id.value for record in records) == ("vp_001", "vp_002")


@pytest.mark.asyncio
async def test_revision_lineage_preservation() -> None:
    operation, registry = await _build_operation(include_replacement=True)

    _ = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(
            existing_voiceprint_id="vp_001",
            new_voiceprint_id="vp_002",
        )
    )

    previous = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    active = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_002"))
    assert previous.lineage.lineage_root_id == VoiceprintId.parse("vp_001")
    assert active.lineage.lineage_root_id == VoiceprintId.parse("vp_001")
    assert active.lineage.parent_voiceprint_id == VoiceprintId.parse("vp_001")
    assert active.lineage.supersedes == VoiceprintId.parse("vp_001")


@pytest.mark.asyncio
async def test_no_direct_mutation_bypass() -> None:
    previous = create_voiceprint_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
        active=False,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
        superseded_by="vp_002",
    )
    active = create_voiceprint_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        subject_id="person_001",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    )
    pre_delete = create_voiceprint_record(
        voiceprint_id="vp_003",
        artifact_id="artifact_003",
        subject_id="person_002",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_003",
    )
    deleted = create_voiceprint_record(
        voiceprint_id="vp_003",
        artifact_id="artifact_003",
        subject_id="person_002",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.DELETED,
        active=False,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id="vp_003",
    )

    registry = _GuardRegistry(records=(pre_delete, previous, active))
    lifecycle = _GuardLifecycleManager(deleted_record=deleted)
    revision = _GuardRevisionManager(previous_record=previous, active_record=active)

    operation = DeleteSupersedeVoiceprintOperation.create(
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )

    delete_result = await operation.delete_voiceprint(
        DeleteVoiceprintRequest.create(voiceprint_id="vp_003")
    )
    supersede_result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(existing_voiceprint_id="vp_001", new_voiceprint_id="vp_002")
    )

    assert delete_result.success is True
    assert supersede_result.success is True
    assert registry.update_calls == 0
    assert registry.register_calls == 0
    assert lifecycle.delete_calls == 1
    assert revision.coordinate_calls == 1


@pytest.mark.asyncio
async def test_safe_diagnostics() -> None:
    operation, _ = await _build_operation()

    result = await operation.delete_voiceprint(
        DeleteVoiceprintRequest.create(
            voiceprint_id="vp_missing",
            request_metadata={"path": "C:/secret", "token": "secret-token", "source": "concierge"},
        )
    )

    assert result.success is False
    assert "path" not in result.safe_diagnostics
    assert "token" not in result.safe_diagnostics


@pytest.mark.asyncio
async def test_no_payload_or_exception_leakage() -> None:
    operation, registry = await _build_operation()
    operation = DeleteSupersedeVoiceprintOperation.create(
        registry=registry,
        lifecycle_manager=_RaisingLifecycleManager(),
        revision_manager=VoiceprintRevisionManager.create(
            registry=registry,
            lifecycle_manager=VoiceprintLifecycleManager.create(registry=registry),
        ),
    )

    result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_001"))
    rendered = str(result)
    assert "Traceback" not in rendered
    assert "secret" not in rendered
    assert "payload" not in rendered


@pytest.mark.asyncio
async def test_runtime_loaded_and_not_loaded_paths() -> None:
    operation, _ = await _build_operation()

    loaded_result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_001"))
    operation.clear()
    not_loaded_result = await operation.delete_voiceprint(DeleteVoiceprintRequest.create(voiceprint_id="vp_001"))

    assert loaded_result.success is True
    assert not_loaded_result.success is False
    assert not_loaded_result.failure_category is DeleteSupersedeFailureCategory.OPERATION_NOT_LOADED


@pytest.mark.asyncio
async def test_internal_error_normalization_supersede() -> None:
    operation, registry = await _build_operation(include_replacement=True)
    operation = DeleteSupersedeVoiceprintOperation.create(
        registry=registry,
        lifecycle_manager=VoiceprintLifecycleManager.create(registry=registry),
        revision_manager=_RaisingRevisionManager(),
    )

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(existing_voiceprint_id="vp_001", new_voiceprint_id="vp_002")
    )

    assert result.success is False
    assert result.failure_category is DeleteSupersedeFailureCategory.OPERATION_INTERNAL_ERROR
    assert result.reason_code == "operation_internal_error"


@pytest.mark.asyncio
async def test_health_registration_shape() -> None:
    operation, _ = await _build_operation()

    health = await operation.validate_health()

    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("delete_voiceprint_ready", "supersede_voiceprint_ready")


@pytest.mark.asyncio
async def test_concierge_consumer_compatibility() -> None:
    operation, _ = await _build_operation(include_replacement=True)

    result = await operation.supersede_voiceprint(
        SupersedeVoiceprintRequest.create(existing_voiceprint_id="vp_001", new_voiceprint_id="vp_002")
    )

    assert result.success is True
    payload = asdict(result)
    assert payload["previous_voiceprint_id"] == "vp_001"
    assert payload["active_voiceprint_id"] == "vp_002"
    assert payload["lifecycle_changes"]["previous_lifecycle_status"] == "superseded"
    assert isinstance(payload["revision_information"]["active_revision"], int)


@pytest.mark.asyncio
async def test_service_contract_compatibility_projection() -> None:
    operation, _ = await _build_operation()

    delete_result = await operation.delete_voiceprint(
        DeleteVoiceprintRequest.create(
            voiceprint_id="vp_001",
            correlation_id="corr_116",
            reason="cleanup",
            request_metadata={"source": "concierge"},
        )
    )

    assert delete_result.success is True
    assert delete_result.operation_id.startswith("op_")
    assert delete_result.operation_status is VoiceprintOperationStatus.COMPLETED
