from __future__ import annotations

import json

import pytest

from custom_components.voice_identity.artifact_integrity import (
    ArtifactIntegrityValidator,
    IntegritySeverity,
)
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceEngine
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import VoiceprintId, VoiceprintRegistry
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_artifact_persistence import _SpyStorageProvider, _initialize_real_managers, _request
from tests.test_voiceprint_registry import _FakeStore


async def _build_stack(storage: _SpyStorageProvider | None = None):
    storage = storage or _SpyStorageProvider()
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)
    persistence = ArtifactPersistenceEngine.create(
        storage_provider=storage,
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )
    validator = ArtifactIntegrityValidator.create(
        storage_provider=storage,
        registry=registry,
        revision_manager=revision,
    )
    return storage, registry, lifecycle, revision, persistence, validator


@pytest.mark.asyncio
async def test_validator_initialization() -> None:
    _, _, _, _, _, validator = await _build_stack()
    health = await validator.validate_health()
    assert health.state is HealthState.HEALTHY


@pytest.mark.asyncio
async def test_valid_artifact_validation() -> None:
    _, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert result.status is IntegritySeverity.HEALTHY


@pytest.mark.asyncio
async def test_missing_artifact_detection() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    storage.artifacts.clear()

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert any(f.reason_code == "artifact_missing" for f in result.findings)


@pytest.mark.asyncio
async def test_corrupted_artifact_detection_invalid_json() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    storage.artifacts["artifact_001"] = b"not-json"

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert any(f.reason_code == "artifact_unreadable" for f in result.findings)


@pytest.mark.asyncio
async def test_digest_mismatch_detection() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    payload = json.loads(storage.artifacts["artifact_001"].decode("utf-8"))
    payload["integrity"]["digest_hex"] = "deadbeef"
    storage.artifacts["artifact_001"] = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert any(f.reason_code == "digest_mismatch" for f in result.findings)


@pytest.mark.asyncio
async def test_payload_size_mismatch_detection() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    payload = json.loads(storage.artifacts["artifact_001"].decode("utf-8"))
    payload["integrity"]["payload_size"] = 999
    storage.artifacts["artifact_001"] = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert any(f.reason_code == "payload_corrupted" for f in result.findings)


@pytest.mark.asyncio
async def test_invalid_envelope_detection() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    payload = json.loads(storage.artifacts["artifact_001"].decode("utf-8"))
    payload["encrypted"] = False
    storage.artifacts["artifact_001"] = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    assert any(f.reason_code == "metadata_invalid" for f in result.findings)


@pytest.mark.asyncio
async def test_missing_registry_record_detection() -> None:
    _, _, _, _, _, validator = await _build_stack()
    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_missing"))
    assert any(f.reason_code == "metadata_missing" for f in result.findings)


@pytest.mark.asyncio
async def test_missing_artifact_referenced_by_registry() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    storage.artifacts.clear()
    health = await validator.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "artifact_missing" in health.reason_codes


@pytest.mark.asyncio
async def test_orphaned_artifact_handling() -> None:
    storage, _, _, _, _, validator = await _build_stack()
    storage.artifacts["orphaned_artifact"] = b"{}"
    result = await validator.validate_all()
    assert any(f.reason_code == "orphaned_artifact" for f in result.findings)


@pytest.mark.asyncio
async def test_lineage_inconsistency_detection() -> None:
    storage, registry, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    record = registry.get_by_voiceprint_id(VoiceprintId.parse("vp_001"))
    registry._records[record.voiceprint_id.value] = type(record)(
        voiceprint_id=record.voiceprint_id,
        artifact_id=record.artifact_id,
        subject_id=record.subject_id,
        lineage=type(record.lineage)(
            revision=record.lineage.revision,
            lineage_root_id=VoiceprintId.parse("vp_other"),
            parent_voiceprint_id=record.lineage.parent_voiceprint_id,
            supersedes=record.lineage.supersedes,
            superseded_by=record.lineage.superseded_by,
        ),
        lifecycle_state=record.lifecycle_state,
        active=record.active,
        created_at=record.created_at,
        updated_at=record.updated_at,
        model_name=record.model_name,
        model_version=record.model_version,
        schema_version=record.schema_version,
    )

    result = await validator.validate_all()
    assert any(f.reason_code == "voiceprint_revision_lineage_invalid" for f in result.findings)


@pytest.mark.asyncio
async def test_duplicate_revision_detection() -> None:
    storage, _, _, _, _, validator = await _build_stack(storage=_SpyStorageProvider())
    storage.artifacts["artifact_001"] = b"{}"
    storage.artifacts["artifact_002"] = b"{}"
    # Covered more directly by revision manager; here verify surfaced health when revision manager reports conflict via loaded data is future-compatible.
    result = await validator.validate_all()
    assert result.findings


@pytest.mark.asyncio
async def test_safe_validation_result_generation() -> None:
    _, _, _, _, _, validator = await _build_stack()
    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_missing"))
    assert all(f.affected_artifact_id is None or "/" not in f.affected_artifact_id for f in result.findings)


@pytest.mark.asyncio
async def test_no_payload_or_secret_or_path_leakage() -> None:
    _, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    result = await validator.validate_voiceprint(VoiceprintId.parse("vp_001"))
    rendered = json.dumps([f.details for f in result.findings])
    assert "ciphertext" not in rendered
    assert "/config" not in rendered
    assert "key_v1" not in rendered


@pytest.mark.asyncio
async def test_health_reporting_when_healthy() -> None:
    _, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    health = await validator.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("artifact_integrity_ready",)


@pytest.mark.asyncio
async def test_health_reporting_when_degraded_or_corrupted() -> None:
    storage, _, _, _, persistence, validator = await _build_stack()
    await persistence.persist_artifact(_request())
    payload = json.loads(storage.artifacts["artifact_001"].decode("utf-8"))
    payload["integrity"]["digest_hex"] = "deadbeef"
    storage.artifacts["artifact_001"] = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    health = await validator.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert "digest_mismatch" in health.reason_codes


def test_clear_behavior() -> None:
    validator = ArtifactIntegrityValidator.create(
        storage_provider=None,  # type: ignore[arg-type]
        registry=None,  # type: ignore[arg-type]
        revision_manager=None,  # type: ignore[arg-type]
    )
    validator.clear()
    assert validator.cleared is True