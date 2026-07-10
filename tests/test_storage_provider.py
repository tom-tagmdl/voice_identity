from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.storage_provider import (
    LocalFileVoiceprintStorageProvider,
    VoiceIdentityStorageArtifactNotFoundError,
    VoiceIdentityStorageIdentifierError,
    VoiceIdentityStorageUnavailableError,
    VoiceprintArtifactId,
)


class _Entry:
    entry_id = "entry"
    data: dict[str, object]
    options: dict[str, object]

    def __init__(self, *, data: dict[str, object] | None = None) -> None:
        self.data = data or {}
        self.options = {}


def _build_provider(tmp_path: Path, *, base_path: str = "voice_identity") -> LocalFileVoiceprintStorageProvider:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(_Entry(data={"storage": {"base_path": base_path}}))
    return LocalFileVoiceprintStorageProvider.from_configuration_manager(
        config_manager=manager,
        ha_config_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_local_provider_initialization(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    metadata = provider.metadata()

    assert metadata.provider_name == "local_filesystem"
    assert metadata.durable_storage is True
    assert metadata.binary_safe is True


@pytest.mark.asyncio
async def test_storage_root_creation(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    health = await provider.validate_availability()

    assert health.state is HealthState.HEALTHY
    assert "storage_ready" in health.reason_codes


@pytest.mark.asyncio
async def test_save_and_load_artifact(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    artifact_id = VoiceprintArtifactId.parse("voiceprint_001")

    await provider.save_artifact(artifact_id, b"artifact-bytes")
    loaded = await provider.load_artifact(artifact_id)

    assert loaded == b"artifact-bytes"


@pytest.mark.asyncio
async def test_delete_artifact(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    artifact_id = VoiceprintArtifactId.parse("voiceprint_002")

    await provider.save_artifact(artifact_id, b"delete-me")
    deleted = await provider.delete_artifact(artifact_id)

    assert deleted is True
    assert await provider.artifact_exists(artifact_id) is False


@pytest.mark.asyncio
async def test_check_artifact_exists(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    artifact_id = VoiceprintArtifactId.parse("voiceprint_003")

    assert await provider.artifact_exists(artifact_id) is False
    await provider.save_artifact(artifact_id, b"exists")
    assert await provider.artifact_exists(artifact_id) is True


@pytest.mark.asyncio
async def test_list_artifacts(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    a = VoiceprintArtifactId.parse("voiceprint_a")
    b = VoiceprintArtifactId.parse("voiceprint_b")
    await provider.save_artifact(a, b"a")
    await provider.save_artifact(b, b"bb")

    artifacts = await provider.list_artifacts()

    assert tuple(item.artifact_id.value for item in artifacts) == ("voiceprint_a", "voiceprint_b")
    assert tuple(item.size_bytes for item in artifacts) == (1, 2)


@pytest.mark.asyncio
async def test_path_traversal_rejection_via_invalid_base_path(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path, base_path="../escape")
    health = await provider.validate_availability()

    assert health.state is HealthState.UNAVAILABLE
    assert "storage_path_invalid" in health.reason_codes


def test_invalid_artifact_identifier_rejection() -> None:
    with pytest.raises(VoiceIdentityStorageIdentifierError):
        VoiceprintArtifactId.parse("../bad")


@pytest.mark.asyncio
async def test_missing_artifact_handling(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    artifact_id = VoiceprintArtifactId.parse("missing_artifact")

    with pytest.raises(VoiceIdentityStorageArtifactNotFoundError):
        await provider.load_artifact(artifact_id)

    assert await provider.delete_artifact(artifact_id) is False


@pytest.mark.asyncio
async def test_storage_provider_health_ready(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path)
    health = await provider.validate_availability()

    assert health.state is HealthState.HEALTHY
    assert health.details["provider"] == "local_filesystem"


@pytest.mark.asyncio
async def test_storage_provider_health_invalid_path(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path, base_path="../invalid")
    health = await provider.validate_availability()

    assert health.state is HealthState.UNAVAILABLE
    assert "storage_path_invalid" in health.reason_codes


@pytest.mark.asyncio
async def test_unavailable_provider_raises_safe_error(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path, base_path="../invalid")

    with pytest.raises(VoiceIdentityStorageUnavailableError):
        await provider.list_artifacts()


@pytest.mark.asyncio
async def test_no_filesystem_detail_leakage_in_health_snapshot(tmp_path: Path) -> None:
    provider = _build_provider(tmp_path, base_path="../invalid")
    health = await provider.validate_availability()

    detail_text = " ".join(str(v) for v in health.details.values()).lower()

    assert all("/" not in reason for reason in health.reason_codes)
    assert all(":" not in reason for reason in health.reason_codes)
    assert "config" not in detail_text