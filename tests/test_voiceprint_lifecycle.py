from __future__ import annotations

import pytest

from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import (
    VoiceprintLifecycleConflictError,
    VoiceprintLifecycleInvalidTransitionError,
    VoiceprintLifecycleManager,
    VoiceprintLifecycleNotLoadedError,
    VoiceprintLifecycleSupersessionError,
)
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    VoiceprintRegistryRecordNotFoundError,
    create_voiceprint_record,
)
from tests.test_voiceprint_registry import _FakeStore, _FakeStorageProvider


async def _build_registry_and_manager(existing_artifacts: set[str]):
    registry = VoiceprintRegistry(
        store=_FakeStore(),
        storage_provider=_FakeStorageProvider(existing_artifacts=existing_artifacts),
    )
    await registry.async_load()
    manager = VoiceprintLifecycleManager.create(registry=registry)
    return registry, manager


def _record(
    *,
    voiceprint_id: str,
    artifact_id: str,
    subject_id: str = "person_001",
    revision: int = 1,
    lifecycle_state: VoiceprintLifecycleState,
    active: bool,
    lineage_root_id: str | None = None,
    parent_voiceprint_id: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
):
    return create_voiceprint_record(
        voiceprint_id=voiceprint_id,
        artifact_id=artifact_id,
        subject_id=subject_id,
        revision=revision,
        lifecycle_state=lifecycle_state,
        active=active,
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        lineage_root_id=lineage_root_id,
        parent_voiceprint_id=parent_voiceprint_id,
        supersedes=supersedes,
        superseded_by=superseded_by,
    )


@pytest.mark.asyncio
async def test_lifecycle_manager_initialization() -> None:
    _, manager = await _build_registry_and_manager(set())
    health = await manager.validate_health()
    assert health.state is HealthState.HEALTHY


@pytest.mark.asyncio
async def test_pending_to_active_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
        )
    )

    updated = await manager.activate_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.ACTIVE
    assert updated.active is True


@pytest.mark.asyncio
async def test_pending_to_failed_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
        )
    )

    updated = await manager.mark_failed(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.FAILED
    assert updated.active is False


@pytest.mark.asyncio
async def test_invalid_lifecycle_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.FAILED,
            active=False,
        )
    )

    with pytest.raises(VoiceprintLifecycleInvalidTransitionError):
        await manager.activate_record(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_active_to_superseded_and_new_active() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001", "artifact_002"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
    )
    await registry.register_record(
        _record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            revision=2,
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
            lineage_root_id="vp_001",
            parent_voiceprint_id="vp_001",
            supersedes="vp_001",
        )
    )

    old_record, new_record = await manager.supersede_record(
        current_voiceprint_id=VoiceprintId.parse("vp_001"),
        replacement_voiceprint_id=VoiceprintId.parse("vp_002"),
    )

    assert old_record.lifecycle_state is VoiceprintLifecycleState.SUPERSEDED
    assert old_record.active is False
    assert old_record.lineage.superseded_by == VoiceprintId.parse("vp_002")
    assert new_record.lifecycle_state is VoiceprintLifecycleState.ACTIVE
    assert new_record.active is True
    assert new_record.lineage.supersedes == VoiceprintId.parse("vp_001")


@pytest.mark.asyncio
async def test_active_to_deleted_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
    )

    updated = await manager.delete_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.DELETED
    assert updated.active is False


@pytest.mark.asyncio
async def test_active_to_inactive_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
    )

    updated = await manager.deactivate_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.INACTIVE
    assert updated.active is False


@pytest.mark.asyncio
async def test_superseded_to_deleted_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
            active=False,
        )
    )

    updated = await manager.delete_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.DELETED


@pytest.mark.asyncio
async def test_inactive_to_active_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.INACTIVE,
            active=False,
        )
    )

    updated = await manager.activate_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.ACTIVE
    assert updated.active is True


@pytest.mark.asyncio
async def test_inactive_to_deleted_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.INACTIVE,
            active=False,
        )
    )

    updated = await manager.delete_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.DELETED
    assert updated.active is False


@pytest.mark.asyncio
async def test_failed_to_deleted_transition() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.FAILED,
            active=False,
        )
    )

    updated = await manager.delete_record(VoiceprintId.parse("vp_001"))
    assert updated.lifecycle_state is VoiceprintLifecycleState.DELETED
    assert updated.active is False


@pytest.mark.asyncio
async def test_deleted_cannot_become_active() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.DELETED,
            active=False,
        )
    )

    with pytest.raises(VoiceprintLifecycleInvalidTransitionError):
        await manager.activate_record(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_superseded_cannot_become_active() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
            active=False,
        )
    )

    with pytest.raises(VoiceprintLifecycleInvalidTransitionError):
        await manager.activate_record(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_artifact_ids_remain_immutable_during_transitions() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
        )
    )

    updated = await manager.activate_record(VoiceprintId.parse("vp_001"))
    assert updated.artifact_id.value == "artifact_001"


@pytest.mark.asyncio
async def test_lifecycle_transitions_do_not_modify_artifact_bytes() -> None:
    storage = _FakeStorageProvider(existing_artifacts={"artifact_001"})
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    manager = VoiceprintLifecycleManager.create(registry=registry)
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
        )
    )

    await manager.activate_record(VoiceprintId.parse("vp_001"))
    assert storage.existing_artifacts == {"artifact_001"}


@pytest.mark.asyncio
async def test_single_active_revision_enforcement() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001", "artifact_002"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
    )
    await registry.register_record(
        _record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            lifecycle_state=VoiceprintLifecycleState.INACTIVE,
            active=False,
            lineage_root_id="vp_001",
        )
    )

    with pytest.raises(VoiceprintLifecycleConflictError):
        await manager.activate_record(VoiceprintId.parse("vp_002"))


@pytest.mark.asyncio
async def test_missing_record_handling() -> None:
    _, manager = await _build_registry_and_manager(set())
    with pytest.raises(VoiceprintRegistryRecordNotFoundError):
        await manager.activate_record(VoiceprintId.parse("vp_missing"))


@pytest.mark.asyncio
async def test_invalid_supersession_handling() -> None:
    registry, manager = await _build_registry_and_manager({"artifact_001", "artifact_002"})
    await registry.register_record(
        _record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
    )
    await registry.register_record(
        _record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            lifecycle_state=VoiceprintLifecycleState.PENDING,
            active=False,
            lineage_root_id="vp_001",
            parent_voiceprint_id="vp_001",
        )
    )

    with pytest.raises(VoiceprintLifecycleSupersessionError):
        await manager.supersede_record(
            current_voiceprint_id=VoiceprintId.parse("vp_001"),
            replacement_voiceprint_id=VoiceprintId.parse("vp_002"),
        )


@pytest.mark.asyncio
async def test_safe_reason_codes_and_no_sensitive_details() -> None:
    _, manager = await _build_registry_and_manager(set())
    health = await manager.validate_health()
    assert health.reason_codes == ("voiceprint_lifecycle_ready",)
    assert all("/" not in code for code in health.reason_codes)


@pytest.mark.asyncio
async def test_health_state_when_lifecycle_not_loaded() -> None:
    _, manager = await _build_registry_and_manager(set())
    manager.clear()
    health = await manager.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "voiceprint_lifecycle_not_loaded" in health.reason_codes


def test_clear_behavior() -> None:
    manager = VoiceprintLifecycleManager.create(registry=None)  # type: ignore[arg-type]
    manager.clear()
    assert manager.cleared is True
    with pytest.raises(VoiceprintLifecycleNotLoadedError):
        manager._ensure_loaded()