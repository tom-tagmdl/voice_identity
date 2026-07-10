"""Storage provider abstraction for durable Voiceprint artifacts.

This layer stores and retrieves artifact bytes only and does not implement
voiceprint registry, lifecycle, revision, or generation semantics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from re import compile as re_compile
from tempfile import NamedTemporaryFile
from typing import Protocol

from .configuration import VoiceIdentityConfigurationManager
from .configuration import VoiceIdentityConfigurationError
from .health_state import HealthState

_ARTIFACT_ID_PATTERN = re_compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class VoiceIdentityStorageProviderError(Exception):
    """Base exception for storage provider failures."""


class VoiceIdentityStorageIdentifierError(VoiceIdentityStorageProviderError):
    """Raised when artifact identifiers are invalid."""


class VoiceIdentityStoragePathTraversalError(VoiceIdentityStorageProviderError):
    """Raised when artifact addressing would escape storage root."""


class VoiceIdentityStorageUnavailableError(VoiceIdentityStorageProviderError):
    """Raised when storage is not available for operations."""


class VoiceIdentityStorageArtifactNotFoundError(VoiceIdentityStorageProviderError):
    """Raised when an artifact does not exist."""


class VoiceIdentityStorageReadError(VoiceIdentityStorageProviderError):
    """Raised when artifact reads fail."""


class VoiceIdentityStorageWriteError(VoiceIdentityStorageProviderError):
    """Raised when artifact writes fail."""


class VoiceIdentityStorageDeleteError(VoiceIdentityStorageProviderError):
    """Raised when artifact deletion fails."""


@dataclass(slots=True, frozen=True)
class VoiceprintArtifactId:
    """Validated identifier for one durable voiceprint artifact."""

    value: str

    @classmethod
    def parse(cls, value: str) -> VoiceprintArtifactId:
        normalized = value.strip()
        if not _ARTIFACT_ID_PATTERN.fullmatch(normalized):
            raise VoiceIdentityStorageIdentifierError("invalid_artifact_identifier")
        return cls(value=normalized)


@dataclass(slots=True, frozen=True)
class StoredArtifactInfo:
    """Safe metadata summary for one stored artifact."""

    artifact_id: VoiceprintArtifactId
    size_bytes: int
    modified_at_utc: str


@dataclass(slots=True, frozen=True)
class StorageProviderMetadata:
    """Safe provider metadata for diagnostics and runtime projections."""

    provider_name: str
    durable_storage: bool
    binary_safe: bool
    metadata_version: int = 1


@dataclass(slots=True, frozen=True)
class StorageProviderHealth:
    """Storage provider health snapshot for health engine integration."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class VoiceprintStorageProvider(Protocol):
    """Provider abstraction for durable artifact byte storage."""

    async def save_artifact(self, artifact_id: VoiceprintArtifactId, payload: bytes) -> None:
        """Persist one artifact payload by identifier."""

    async def load_artifact(self, artifact_id: VoiceprintArtifactId) -> bytes:
        """Load one stored artifact payload."""

    async def delete_artifact(self, artifact_id: VoiceprintArtifactId) -> bool:
        """Delete one artifact by identifier."""

    async def artifact_exists(self, artifact_id: VoiceprintArtifactId) -> bool:
        """Return whether artifact exists."""

    async def list_artifacts(self) -> tuple[StoredArtifactInfo, ...]:
        """List stored artifacts."""

    async def validate_availability(self) -> StorageProviderHealth:
        """Validate provider availability and return safe health snapshot."""

    def metadata(self) -> StorageProviderMetadata:
        """Return safe provider metadata."""

    def clear(self) -> None:
        """Clear provider runtime state during unload."""


class LocalFileVoiceprintStorageProvider:
    """Local filesystem provider for durable voiceprint artifact bytes."""

    def __init__(
        self,
        *,
        storage_root: Path | None,
        ready: bool,
        reason_codes: tuple[str, ...],
        details: dict[str, bool | int | float | str | None],
    ) -> None:
        self._storage_root = storage_root
        self._ready = ready
        self._reason_codes = reason_codes
        self._details = details
        self._cleared = False

    @classmethod
    def from_configuration_manager(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        ha_config_dir: Path,
    ) -> LocalFileVoiceprintStorageProvider:
        try:
            base_path = config_manager.config.storage.base_path
        except VoiceIdentityConfigurationError:
            return cls(
                storage_root=None,
                ready=False,
                reason_codes=("storage_not_configured",),
                details={"provider": "local_filesystem", "configured": False},
            )

        root = _build_storage_root(ha_config_dir=ha_config_dir, base_path=base_path)
        if root is None:
            return cls(
                storage_root=None,
                ready=False,
                reason_codes=("storage_path_invalid",),
                details={"provider": "local_filesystem", "configured": False},
            )

        try:
            root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return cls(
                storage_root=None,
                ready=False,
                reason_codes=("storage_permission_denied",),
                details={"provider": "local_filesystem", "configured": True},
            )
        except OSError:
            return cls(
                storage_root=None,
                ready=False,
                reason_codes=("storage_unavailable",),
                details={"provider": "local_filesystem", "configured": True},
            )

        return cls(
            storage_root=root,
            ready=True,
            reason_codes=("storage_ready",),
            details={"provider": "local_filesystem", "configured": True},
        )

    async def save_artifact(self, artifact_id: VoiceprintArtifactId, payload: bytes) -> None:
        path = self._resolve_artifact_path(artifact_id)
        try:
            await asyncio.to_thread(_atomic_write_bytes, path, payload)
        except PermissionError as err:
            raise VoiceIdentityStorageWriteError("storage_permission_denied") from err
        except OSError as err:
            raise VoiceIdentityStorageWriteError("storage_write_failed") from err

    async def load_artifact(self, artifact_id: VoiceprintArtifactId) -> bytes:
        path = self._resolve_artifact_path(artifact_id)

        if not await asyncio.to_thread(path.exists):
            raise VoiceIdentityStorageArtifactNotFoundError("artifact_not_found")

        try:
            return await asyncio.to_thread(path.read_bytes)
        except PermissionError as err:
            raise VoiceIdentityStorageReadError("storage_permission_denied") from err
        except OSError as err:
            raise VoiceIdentityStorageReadError("storage_read_failed") from err

    async def delete_artifact(self, artifact_id: VoiceprintArtifactId) -> bool:
        path = self._resolve_artifact_path(artifact_id)

        if not await asyncio.to_thread(path.exists):
            return False

        try:
            await asyncio.to_thread(path.unlink)
        except PermissionError as err:
            raise VoiceIdentityStorageDeleteError("storage_permission_denied") from err
        except OSError as err:
            raise VoiceIdentityStorageDeleteError("storage_delete_failed") from err
        return True

    async def artifact_exists(self, artifact_id: VoiceprintArtifactId) -> bool:
        path = self._resolve_artifact_path(artifact_id)
        return await asyncio.to_thread(path.exists)

    async def list_artifacts(self) -> tuple[StoredArtifactInfo, ...]:
        root = self._require_root()

        def _scan() -> tuple[StoredArtifactInfo, ...]:
            artifacts: list[StoredArtifactInfo] = []
            for candidate in sorted(root.glob("*.bin")):
                try:
                    artifact_id = VoiceprintArtifactId.parse(candidate.stem)
                except VoiceIdentityStorageIdentifierError:
                    continue

                stat = candidate.stat()
                artifacts.append(
                    StoredArtifactInfo(
                        artifact_id=artifact_id,
                        size_bytes=stat.st_size,
                        modified_at_utc=datetime.fromtimestamp(
                            stat.st_mtime,
                            tz=timezone.utc,
                        ).isoformat(),
                    )
                )
            return tuple(artifacts)

        return await asyncio.to_thread(_scan)

    async def validate_availability(self) -> StorageProviderHealth:
        if not self._ready:
            return StorageProviderHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=self._reason_codes,
                details=dict(self._details),
            )

        root = self._require_root()
        try:
            await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(_probe_write_delete, root)
        except PermissionError:
            return StorageProviderHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("storage_permission_denied",),
                details={"provider": "local_filesystem", "configured": True},
            )
        except OSError:
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

    def metadata(self) -> StorageProviderMetadata:
        return StorageProviderMetadata(
            provider_name="local_filesystem",
            durable_storage=True,
            binary_safe=True,
        )

    def clear(self) -> None:
        self._cleared = True

    @property
    def cleared(self) -> bool:
        """Expose cleared state for lifecycle tests."""
        return self._cleared

    def _require_root(self) -> Path:
        if not self._ready or self._storage_root is None:
            raise VoiceIdentityStorageUnavailableError("storage_unavailable")
        return self._storage_root

    def _resolve_artifact_path(self, artifact_id: VoiceprintArtifactId) -> Path:
        root = self._require_root()
        candidate = (root / f"{artifact_id.value}.bin").resolve()
        try:
            candidate.relative_to(root)
        except ValueError as err:
            raise VoiceIdentityStoragePathTraversalError("storage_path_invalid") from err
        return candidate


def _build_storage_root(ha_config_dir: Path, base_path: str) -> Path | None:
    config_root = ha_config_dir.resolve()
    base = Path(base_path)

    if base.is_absolute():
        return None
    if any(part in {"..", ""} for part in base.parts):
        return None

    root = (config_root / base / "voiceprints").resolve()
    try:
        root.relative_to(config_root)
    except ValueError:
        return None
    return root


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp_file:
        temp_file.write(payload)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def _probe_write_delete(root: Path) -> None:
    probe = root / ".provider_health_probe"
    probe.write_bytes(b"ok")
    probe.unlink(missing_ok=True)
