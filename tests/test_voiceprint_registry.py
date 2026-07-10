from __future__ import annotations

from dataclasses import dataclass

import pytest

from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.storage_provider import VoiceprintArtifactId
from custom_components.voice_identity.voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRegistry,
    VoiceprintRegistryArtifactMutationError,
    VoiceprintRegistryDuplicateError,
    VoiceprintRegistryIdentifierError,
    VoiceprintRegistryValidationError,
    VoiceprintSubjectId,
    create_voiceprint_record,
)


class _FakeStore:
    def __init__(self, initial: dict | None = None) -> None:
        self.saved_payload: dict | None = None
        self.initial = initial

    async def async_load(self):
        return self.initial

    async def async_save(self, payload):
        self.saved_payload = payload


@dataclass
class _FakeStorageProvider:
    existing_artifacts: set[str]

    async def save_artifact(self, artifact_id, payload):
        self.existing_artifacts.add(artifact_id.value)

    async def load_artifact(self, artifact_id):
        return b"artifact"

    async def delete_artifact(self, artifact_id):
        return self.existing_artifacts.discard(artifact_id.value) is None

    async def artifact_exists(self, artifact_id):
        return artifact_id.value in self.existing_artifacts

    async def list_artifacts(self):
        return ()

    async def validate_availability(self):
        raise NotImplementedError

    def metadata(self):
        raise NotImplementedError

    def clear(self):
        return None


async def _build_registry(existing_artifacts: set[str] | None = None, initial: dict | None = None):
    store = _FakeStore(initial=initial)
    storage = _FakeStorageProvider(existing_artifacts=existing_artifacts or set())
    registry = VoiceprintRegistry(store=store, storage_provider=storage)
    await registry.async_load()
    return registry, store, storage


def _record(
    *,
    voiceprint_id: str = "vp_001",
    artifact_id: str = "artifact_001",
    subject_id: str = "person_001",
    revision: int = 1,
    lifecycle_state: VoiceprintLifecycleState = VoiceprintLifecycleState.ACTIVE,
    active: bool = True,
    lineage_root_id: str | None = None,
    parent_voiceprint_id: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
) :
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
async def test_registry_initialization() -> None:
    registry, _, _ = await _build_registry()
    assert registry.list_records() == ()


@pytest.mark.asyncio
async def test_register_valid_voiceprint_record() -> None:
    registry, store, _ = await _build_registry({"artifact_001"})
    record = _record()

    saved = await registry.register_record(record)

    assert saved == record
    assert store.saved_payload is not None


def test_reject_invalid_voiceprint_id() -> None:
    with pytest.raises(VoiceprintRegistryIdentifierError):
        VoiceprintId.parse("../bad")


def test_reject_invalid_or_unsafe_artifact_id() -> None:
    with pytest.raises(Exception):
        create_voiceprint_record(
            voiceprint_id="vp_001",
            artifact_id="../bad",
            subject_id="person_001",
            revision=1,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
        )


@pytest.mark.asyncio
async def test_lookup_by_voiceprint_id() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    record = _record()
    await registry.register_record(record)

    loaded = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    assert loaded.voiceprint_id.value == "vp_001"


@pytest.mark.asyncio
async def test_lookup_by_artifact_id() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    record = _record()
    await registry.register_record(record)

    loaded = registry.get_by_artifact_id(VoiceprintArtifactId.parse("artifact_001"))
    assert loaded is not None
    assert loaded.artifact_id.value == "artifact_001"


@pytest.mark.asyncio
async def test_lookup_by_subject_id() -> None:
    registry, _, _ = await _build_registry({"artifact_001", "artifact_002"})
    first = _record()
    second = _record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        parent_voiceprint_id="vp_001",
        lineage_root_id="vp_001",
    )
    await registry.register_record(first)
    await registry.register_record(second)

    records = registry.get_by_subject_id(VoiceprintSubjectId.parse("person_001"))
    assert tuple(item.voiceprint_id.value for item in records) == ("vp_001", "vp_002")


@pytest.mark.asyncio
async def test_listing_records_is_deterministic() -> None:
    registry, _, _ = await _build_registry({"artifact_b", "artifact_a"})
    await registry.register_record(_record(voiceprint_id="vp_b", artifact_id="artifact_b"))
    await registry.register_record(_record(voiceprint_id="vp_a", artifact_id="artifact_a"))

    records = registry.list_records()
    assert tuple(item.voiceprint_id.value for item in records) == ("vp_a", "vp_b")


@pytest.mark.asyncio
async def test_represent_active_records() -> None:
    registry, _, _ = await _build_registry({"artifact_001", "artifact_002"})
    await registry.register_record(_record())
    await registry.register_record(
        _record(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            active=False,
            lifecycle_state=VoiceprintLifecycleState.INACTIVE,
        )
    )

    active_records = registry.list_active_records()
    assert tuple(item.voiceprint_id.value for item in active_records) == ("vp_001",)


@pytest.mark.asyncio
async def test_represent_superseded_records() -> None:
    registry, _, _ = await _build_registry({"artifact_001", "artifact_002"})
    await registry.register_record(_record())
    superseded = _record(
        voiceprint_id="vp_002",
        artifact_id="artifact_002",
        revision=2,
        active=False,
        lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
        lineage_root_id="vp_001",
        parent_voiceprint_id="vp_001",
        supersedes="vp_001",
    )
    await registry.register_record(superseded)

    snapshot = registry.snapshot()
    target = next(item for item in snapshot.records if item.voiceprint_id == "vp_002")
    assert target.lifecycle_state == VoiceprintLifecycleState.SUPERSEDED.value
    assert target.supersedes == "vp_001"


@pytest.mark.asyncio
async def test_preserve_artifact_immutability() -> None:
    registry, _, _ = await _build_registry({"artifact_001", "artifact_002"})
    await registry.register_record(_record())

    with pytest.raises(VoiceprintRegistryArtifactMutationError):
        await registry.register_record(_record(artifact_id="artifact_002"))


@pytest.mark.asyncio
async def test_duplicate_record_handling() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    record = _record()
    await registry.register_record(record)

    with pytest.raises(VoiceprintRegistryDuplicateError):
        await registry.register_record(record)


def test_lifecycle_state_validation() -> None:
    with pytest.raises(VoiceprintRegistryValidationError):
        create_voiceprint_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            subject_id="person_001",
            revision=1,
            lifecycle_state=VoiceprintLifecycleState.DELETED,
            active=True,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
        )


def test_lineage_metadata_validation() -> None:
    with pytest.raises(VoiceprintRegistryValidationError):
        create_voiceprint_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            subject_id="person_001",
            revision=0,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
        )


@pytest.mark.asyncio
async def test_safe_snapshot_output() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    await registry.register_record(_record())

    snapshot = registry.snapshot()
    target = snapshot.records[0]
    assert target.voiceprint_id == "vp_001"
    assert target.subject_id == "person_001"
    assert target.artifact_id == "artifact_001"


@pytest.mark.asyncio
async def test_no_leakage_of_unsafe_details() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    await registry.register_record(_record())
    health = await registry.validate_health()

    detail_text = " ".join(str(v) for v in health.details.values()).lower()
    assert "/" not in detail_text
    assert "config" not in detail_text


@pytest.mark.asyncio
async def test_health_state_ready() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    await registry.register_record(_record())

    health = await registry.validate_health()
    assert health.state is HealthState.HEALTHY
    assert "voiceprint_registry_ready" in health.reason_codes


@pytest.mark.asyncio
async def test_health_state_when_artifact_missing() -> None:
    registry, _, _ = await _build_registry({"artifact_001"})
    await registry.register_record(_record())
    registry._storage_provider.existing_artifacts.clear()  # type: ignore[attr-defined]

    health = await registry.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "voiceprint_artifact_missing" in health.reason_codes


@pytest.mark.asyncio
async def test_compatibility_with_vi104_storage_provider_contract() -> None:
    registry, _, storage = await _build_registry({"artifact_001"})
    await registry.register_record(_record())

    assert await storage.artifact_exists(VoiceprintArtifactId.parse("artifact_001")) is True


@pytest.mark.asyncio
async def test_load_from_persisted_payload() -> None:
    persisted = {
        "records": [
            {
                "voiceprint_id": "vp_001",
                "artifact_id": "artifact_001",
                "subject_id": "person_001",
                "revision": 1,
                "lineage_root_id": "vp_001",
                "parent_voiceprint_id": None,
                "supersedes": None,
                "superseded_by": None,
                "lifecycle_state": "active",
                "active": True,
                "created_at": "2026-07-09T00:00:00+00:00",
                "updated_at": "2026-07-09T00:00:00+00:00",
                "model_name": "ecapa",
                "model_version": "v1",
                "schema_version": 1,
            }
        ]
    }
    registry, _, _ = await _build_registry({"artifact_001"}, initial=persisted)
    assert registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001")).artifact_id.value == "artifact_001"
