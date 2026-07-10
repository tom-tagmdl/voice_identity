from __future__ import annotations

from dataclasses import dataclass

import pytest

from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    VoiceprintRegistryArtifactMutationError,
    create_voiceprint_record,
)
from custom_components.voice_identity.voiceprint_revision import (
    VoiceprintRevisionConflictError,
    VoiceprintRevisionManager,
    VoiceprintRevisionNotLoadedError,
    VoiceprintRevisionValidationError,
)
from tests.test_voiceprint_registry import _FakeStore, _FakeStorageProvider


async def _build_managers(existing_artifacts: set[str]):
    storage = _FakeStorageProvider(existing_artifacts=existing_artifacts)
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)
    return storage, registry, lifecycle, revision


def _record(
    *,
    voiceprint_id: str,
    artifact_id: str,
    subject_id: str = "person_001",
    revision: int,
    lifecycle_state: VoiceprintLifecycleState,
    active: bool,
    lineage_root_id: str | None = None,
    parent_voiceprint_id: str | None = None,
    supersedes: str | None = None,
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
    )


@pytest.mark.asyncio
async def test_revision_manager_initialization() -> None:
    _, _, _, revision = await _build_managers(set())
    health = await revision.validate_health()
    assert health.state is HealthState.HEALTHY


@pytest.mark.asyncio
async def test_first_revision_number_calculation() -> None:
    _, _, _, revision = await _build_managers(set())
    assert revision.get_next_revision() == 1


@pytest.mark.asyncio
async def test_next_revision_number_calculation() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001"})
    root = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    await registry.register_record(root)
    assert revision.get_next_revision(VoiceprintId.parse("vp_001")) == 2


@pytest.mark.asyncio
async def test_deterministic_revision_increments() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(
        revision.prepare_initial_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            subject_id="person_001",
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
        )
    )
    next_record = revision.prepare_next_revision_record(
        current_voiceprint_id=VoiceprintId.parse("vp_001"),
        new_voiceprint_id="vp_002",
        new_artifact_id="artifact_002",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    assert next_record.lineage.revision == 2


@pytest.mark.asyncio
async def test_duplicate_revision_rejection() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.INACTIVE,
        active=False,
        lineage_root_id="vp_001",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_revision_gap_detection() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_003"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_003",
        artifact_id="artifact_003",
        revision=3,
        lifecycle_state=VoiceprintLifecycleState.INACTIVE,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_immutable_revision_identity_preservation() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001"})
    record = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    await registry.register_record(record)

    with pytest.raises(VoiceprintRegistryArtifactMutationError):
        await registry.update_record(_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            revision=2,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        ))


@pytest.mark.asyncio
async def test_immutable_artifact_id_preservation() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    record = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    await registry.register_record(record)

    with pytest.raises(VoiceprintRegistryArtifactMutationError):
        await registry.update_record(_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_002",
            revision=1,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        ))


@pytest.mark.asyncio
async def test_root_lineage_creation() -> None:
    _, _, _, revision = await _build_managers(set())
    record = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    assert record.lineage.lineage_root_id == VoiceprintId.parse("vp_001")
    assert record.lineage.parent_voiceprint_id is None


@pytest.mark.asyncio
async def test_child_revision_creation_or_preparation() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    root = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    await registry.register_record(root)

    child = revision.prepare_next_revision_record(
        current_voiceprint_id=VoiceprintId.parse("vp_001"),
        new_voiceprint_id="vp_002",
        new_artifact_id="artifact_002",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    assert child.lineage.parent_voiceprint_id == VoiceprintId.parse("vp_001")
    assert child.lineage.supersedes == VoiceprintId.parse("vp_001")


@pytest.mark.asyncio
async def test_parent_revision_validation_and_missing_parent_rejection() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_missing",
        supersedes="vp_001",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_supersedes_relationship_validation() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_wrong",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_supersession_chain_validation_and_lineage_intact() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002", "artifact_003"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
        active=False,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_003",
        artifact_id="artifact_003",
        revision=3,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_002",
        supersedes="vp_002",
    ))

    chain = revision.traverse_lineage(VoiceprintId.parse("vp_001"))
    assert tuple(item.voiceprint_id.value for item in chain) == ("vp_001", "vp_002", "vp_003")


@pytest.mark.asyncio
async def test_detection_of_conflicting_lineage_roots() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_other",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_other"))


@pytest.mark.asyncio
async def test_coordinate_supersession_uses_lifecycle_manager() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    ))

    old_record, new_record = await revision.coordinate_supersession(
        current_voiceprint_id=VoiceprintId.parse("vp_001"),
        replacement_voiceprint_id=VoiceprintId.parse("vp_002"),
    )
    assert old_record.lifecycle_state is VoiceprintLifecycleState.SUPERSEDED
    assert new_record.lifecycle_state is VoiceprintLifecycleState.ACTIVE


@pytest.mark.asyncio
async def test_coordinate_supersession_delegates_to_lifecycle_manager() -> None:
    @dataclass
    class _FakeLifecycleManager:
        called: bool = False

        async def supersede_record(self, *, current_voiceprint_id, replacement_voiceprint_id):
            self.called = True
            return current_voiceprint_id, replacement_voiceprint_id

    _, registry, _, _ = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    ))
    fake_lifecycle = _FakeLifecycleManager()
    revision = VoiceprintRevisionManager.create(
        registry=registry,
        lifecycle_manager=fake_lifecycle,  # type: ignore[arg-type]
    )

    current, replacement = await revision.coordinate_supersession(
        current_voiceprint_id=VoiceprintId.parse("vp_001"),
        replacement_voiceprint_id=VoiceprintId.parse("vp_002"),
    )

    assert fake_lifecycle.called is True
    assert current == VoiceprintId.parse("vp_001")
    assert replacement == VoiceprintId.parse("vp_002")


@pytest.mark.asyncio
async def test_no_artifact_byte_mutation() -> None:
    storage, registry, _, revision = await _build_managers({"artifact_001"})
    root = revision.prepare_initial_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
    )
    await registry.register_record(root)
    _ = revision.get_next_revision(VoiceprintId.parse("vp_001"))
    assert storage.existing_artifacts == {"artifact_001"}


@pytest.mark.asyncio
async def test_cycle_detection_if_parent_chain_loops() -> None:
    _, registry, _, revision = await _build_managers({"artifact_001", "artifact_002"})
    await registry.register_record(_record(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lifecycle_state=VoiceprintLifecycleState.ACTIVE,
        active=True,
    ))
    await registry.register_record(_record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        lifecycle_state=VoiceprintLifecycleState.PENDING,
        active=False,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_002",
        supersedes="vp_001",
    ))

    with pytest.raises(VoiceprintRevisionConflictError):
        revision.validate_revision_sequence(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_safe_reason_codes_and_no_sensitive_details() -> None:
    _, _, _, revision = await _build_managers(set())
    health = await revision.validate_health()
    assert health.reason_codes == ("voiceprint_revision_ready",)
    assert all("/" not in code for code in health.reason_codes)


@pytest.mark.asyncio
async def test_health_state_when_revision_manager_not_loaded() -> None:
    _, _, _, revision = await _build_managers(set())
    revision.clear()
    health = await revision.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "voiceprint_revision_not_loaded" in health.reason_codes


def test_clear_behavior() -> None:
    manager = VoiceprintRevisionManager.create(registry=None, lifecycle_manager=None)  # type: ignore[arg-type]
    manager.clear()
    assert manager.cleared is True
    with pytest.raises(VoiceprintRevisionNotLoadedError):
        manager._ensure_loaded()