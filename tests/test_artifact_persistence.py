from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from custom_components.voice_identity.artifact_persistence import (
    ArtifactPersistenceEngine,
    ArtifactPersistenceLifecycleError,
    ArtifactPersistencePayloadError,
    ArtifactPersistenceRegistryError,
    ArtifactPersistenceRevisionError,
    ArtifactPersistenceStorageError,
    PersistArtifactRequest,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_registry import VoiceprintId, VoiceprintLifecycleState
from tests.test_voiceprint_registry import _FakeStore
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistry, create_voiceprint_record
from custom_components.voice_identity.voiceprint_lifecycle import (
    VoiceprintLifecycleError,
    VoiceprintLifecycleManager,
)
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager


@dataclass
class _SpyStorageProvider:
    artifacts: dict[str, bytes] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    load_calls: list[str] = field(default_factory=list)
    delete_calls: list[str] = field(default_factory=list)
    fail_save: bool = False
    fail_load: bool = False
    fail_delete: bool = False
    unavailable: bool = False

    async def save_artifact(self, artifact_id, payload):
        self.save_calls.append(artifact_id.value)
        if self.fail_save:
            from custom_components.voice_identity.storage_provider import VoiceIdentityStorageWriteError

            raise VoiceIdentityStorageWriteError("storage_write_failed")
        self.artifacts[artifact_id.value] = payload

    async def load_artifact(self, artifact_id):
        self.load_calls.append(artifact_id.value)
        if self.fail_load or artifact_id.value not in self.artifacts:
            from custom_components.voice_identity.storage_provider import VoiceIdentityStorageArtifactNotFoundError

            raise VoiceIdentityStorageArtifactNotFoundError("artifact_not_found")
        return self.artifacts[artifact_id.value]

    async def delete_artifact(self, artifact_id):
        self.delete_calls.append(artifact_id.value)
        if self.fail_delete:
            from custom_components.voice_identity.storage_provider import VoiceIdentityStorageDeleteError

            raise VoiceIdentityStorageDeleteError("storage_delete_failed")
        return self.artifacts.pop(artifact_id.value, None) is not None

    async def artifact_exists(self, artifact_id):
        return artifact_id.value in self.artifacts

    async def list_artifacts(self):
        return ()

    async def validate_availability(self):
        from custom_components.voice_identity.storage_provider import StorageProviderHealth

        if self.unavailable:
            return StorageProviderHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("storage_unavailable",),
                details={"provider": "local_filesystem", "configured": True},
            )
        return StorageProviderHealth(
            state=HealthState.HEALTHY,
            reason_codes=("storage_ready",),
            details={"provider": "local_filesystem", "configured": True},
        )

    def metadata(self):
        raise NotImplementedError

    def clear(self):
        return None


def _build_real_managers(storage: _SpyStorageProvider):
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)
    return registry, lifecycle, revision


async def _initialize_real_managers(storage: _SpyStorageProvider):
    registry, lifecycle, revision = _build_real_managers(storage)
    await registry.async_load()
    return registry, lifecycle, revision


def _request(**overrides):
    base = PersistArtifactRequest(
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        subject_id="person_001",
        current_voiceprint_id=None,
        encrypted=True,
        encrypted_payload=b"ciphertext",
        payload_format_version=1,
        encryption_scheme="aes_gcm_v1",
        key_reference="key_v1",
        model_name="ecapa",
        model_version="v1",
        schema_version=1,
        activate=True,
    )
    return PersistArtifactRequest(**{**base.__dict__, **overrides})


@pytest.mark.asyncio
async def test_persistence_engine_initialization() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(
        storage_provider=storage,
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )
    health = await engine.validate_health()
    assert health.state is HealthState.HEALTHY


@pytest.mark.asyncio
async def test_persist_valid_encrypted_representation_payload() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    result = await engine.persist_artifact(_request())

    assert result.voiceprint_id == "vp_001"
    assert result.artifact_id == "artifact_001"
    assert result.active is True
    assert storage.save_calls == ["artifact_001"]


@pytest.mark.asyncio
async def test_reject_plaintext_or_invalid_payloads() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistencePayloadError):
        await engine.persist_artifact(_request(encrypted=False))


@pytest.mark.asyncio
async def test_reject_unsafe_metadata() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistencePayloadError):
        await engine.persist_artifact(_request(encryption_scheme="AES GCM"))


@pytest.mark.asyncio
async def test_generates_integrity_metadata() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    result = await engine.persist_artifact(_request())
    assert result.integrity.digest_algorithm == "sha256"
    assert result.integrity.payload_size == len(b"ciphertext")


@pytest.mark.asyncio
async def test_saving_artifact_bytes_through_storage_only() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())
    assert storage.save_calls == ["artifact_001"]


@pytest.mark.asyncio
async def test_loading_persisted_artifact() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())

    loaded = await engine.load_artifact(VoiceprintId.parse("vp_001"))
    assert loaded.voiceprint_id == "vp_001"
    assert loaded.envelope.encrypted_payload == b"ciphertext"


@pytest.mark.asyncio
async def test_handling_missing_registry_metadata() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistenceRegistryError):
        await engine.load_artifact(VoiceprintId.parse("vp_missing"))


@pytest.mark.asyncio
async def test_handling_missing_artifact_bytes() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    await registry.register_record(
        create_voiceprint_record(
            voiceprint_id="vp_001",
            artifact_id="artifact_001",
            subject_id="person_001",
            revision=1,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
            model_name="ecapa",
            model_version="v1",
            schema_version=1,
        )
    )
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistenceStorageError):
        await engine.load_artifact(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_delete_artifact_metadata_and_bytes() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())

    result = await engine.delete_artifact(VoiceprintId.parse("vp_001"))
    assert result.artifact_deleted is True
    assert result.lifecycle_state == VoiceprintLifecycleState.DELETED.value


@pytest.mark.asyncio
async def test_artifact_and_revision_identity_remain_immutable() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())
    record = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    assert record.artifact_id.value == "artifact_001"
    assert record.lineage.revision == 1


@pytest.mark.asyncio
async def test_handles_storage_save_failure() -> None:
    storage = _SpyStorageProvider(fail_save=True)
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistenceStorageError):
        await engine.persist_artifact(_request())


@pytest.mark.asyncio
async def test_handles_registry_registration_failure() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())

    with pytest.raises(ArtifactPersistenceRegistryError):
        await engine.persist_artifact(_request(artifact_id="artifact_002"))


@pytest.mark.asyncio
async def test_rejects_overwrite_of_existing_immutable_artifact_id() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())

    with pytest.raises(ArtifactPersistenceStorageError):
        await engine.persist_artifact(_request(voiceprint_id="vp_002", current_voiceprint_id="vp_001", subject_id=None))


@pytest.mark.asyncio
async def test_handles_lifecycle_activation_failure() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    @dataclass
    class _FailingLifecycleManager:
        async def activate_record(self, voiceprint_id):
            raise VoiceprintLifecycleError("fail")

        async def delete_record(self, voiceprint_id):
            _ = voiceprint_id
            raise VoiceprintLifecycleError("fail")

        async def supersede_record(self, **kwargs):
            _ = kwargs
            raise VoiceprintLifecycleError("fail")

        async def validate_health(self):
            return type("LifecycleHealth", (), {"state": HealthState.HEALTHY, "reason_codes": (), "details": {}})()

    real_engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await real_engine.persist_artifact(_request())

    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=_FailingLifecycleManager(), revision_manager=revision)  # type: ignore[arg-type]

    with pytest.raises(ArtifactPersistenceLifecycleError):
        await engine.persist_artifact(_request(
            voiceprint_id="vp_002",
            artifact_id="artifact_002",
            current_voiceprint_id="vp_001",
            subject_id=None,
        ))


@pytest.mark.asyncio
async def test_handles_revision_preparation_failure() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)

    with pytest.raises(ArtifactPersistenceRevisionError):
        await engine.persist_artifact(_request(current_voiceprint_id="vp_missing", subject_id=None))


@pytest.mark.asyncio
async def test_handles_delete_failure() -> None:
    storage = _SpyStorageProvider(fail_delete=True)
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    await engine.persist_artifact(_request())

    with pytest.raises(ArtifactPersistenceStorageError):
        await engine.delete_artifact(VoiceprintId.parse("vp_001"))


@pytest.mark.asyncio
async def test_safe_reason_codes_and_no_payload_or_path_leakage() -> None:
    storage = _SpyStorageProvider()
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    health = await engine.validate_health()
    assert health.reason_codes == ("artifact_persistence_ready",)
    assert all("/" not in code for code in health.reason_codes)


@pytest.mark.asyncio
async def test_health_state_when_unavailable() -> None:
    storage = _SpyStorageProvider(unavailable=True)
    registry, lifecycle, revision = await _initialize_real_managers(storage)
    engine = ArtifactPersistenceEngine.create(storage_provider=storage, registry=registry, lifecycle_manager=lifecycle, revision_manager=revision)
    health = await engine.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "artifact_persistence_save_failed" in health.reason_codes


def test_clear_behavior() -> None:
    engine = ArtifactPersistenceEngine.create(
        storage_provider=None,  # type: ignore[arg-type]
        registry=None,  # type: ignore[arg-type]
        lifecycle_manager=None,  # type: ignore[arg-type]
        revision_manager=None,  # type: ignore[arg-type]
    )
    engine.clear()
    assert engine.cleared is True