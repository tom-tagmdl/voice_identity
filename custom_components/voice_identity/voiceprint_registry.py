"""Voiceprint registry metadata layer.

The registry tracks immutable artifact references and voiceprint metadata above
the storage provider abstraction. It does not store artifact bytes or implement
full lifecycle, revision-policy, or integrity semantics.
"""

from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .health_state import HealthState
from .storage_provider import (
    VoiceIdentityStorageArtifactNotFoundError,
    VoiceprintStorageProvider,
    VoiceprintArtifactId,
)

_VOICEPRINT_ID_PATTERN = re_compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_SUBJECT_ID_PATTERN = re_compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")

VOICEPRINT_REGISTRY_STORE_VERSION = 1
VOICEPRINT_REGISTRY_STORE_KEY = "voice_identity.voiceprint_registry"


class VoiceprintLifecycleState(StrEnum):
    """Lifecycle metadata states for registry records."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"
    DELETED = "deleted"
    PENDING = "pending"
    FAILED = "failed"


class VoiceprintRegistryError(Exception):
    """Base exception for voiceprint registry failures."""


class VoiceprintRegistryIdentifierError(VoiceprintRegistryError):
    """Raised when voiceprint or subject identifiers are invalid."""


class VoiceprintRegistryDuplicateError(VoiceprintRegistryError):
    """Raised when duplicate voiceprint ids are registered."""


class VoiceprintRegistryArtifactMutationError(VoiceprintRegistryError):
    """Raised when an existing artifact association would be mutated."""


class VoiceprintRegistryRecordNotFoundError(VoiceprintRegistryError):
    """Raised when a registry record does not exist."""


class VoiceprintRegistryValidationError(VoiceprintRegistryError):
    """Raised when registry metadata is invalid."""


@dataclass(slots=True, frozen=True)
class VoiceprintId:
    """Validated stable identifier for one voiceprint metadata record."""

    value: str

    @classmethod
    def parse(cls, value: str) -> VoiceprintId:
        normalized = value.strip()
        if not _VOICEPRINT_ID_PATTERN.fullmatch(normalized):
            raise VoiceprintRegistryIdentifierError("invalid_voiceprint_id")
        return cls(value=normalized)


@dataclass(slots=True, frozen=True)
class VoiceprintSubjectId:
    """Validated identity-subject reference for registry indexing."""

    value: str

    @classmethod
    def parse(cls, value: str) -> VoiceprintSubjectId:
        normalized = value.strip()
        if not _SUBJECT_ID_PATTERN.fullmatch(normalized):
            raise VoiceprintRegistryIdentifierError("invalid_subject_id")
        return cls(value=normalized)


@dataclass(slots=True, frozen=True)
class VoiceprintLineage:
    """Revision and lineage metadata for one voiceprint record."""

    revision: int
    lineage_root_id: VoiceprintId
    parent_voiceprint_id: VoiceprintId | None = None
    supersedes: VoiceprintId | None = None
    superseded_by: VoiceprintId | None = None


@dataclass(slots=True, frozen=True)
class VoiceprintRecord:
    """Durable voiceprint registry metadata record."""

    voiceprint_id: VoiceprintId
    artifact_id: VoiceprintArtifactId
    subject_id: VoiceprintSubjectId
    lineage: VoiceprintLineage
    lifecycle_state: VoiceprintLifecycleState
    active: bool
    created_at: str
    updated_at: str
    model_name: str
    model_version: str
    schema_version: int


@dataclass(slots=True, frozen=True)
class VoiceprintRegistrySnapshotRecord:
    """Safe snapshot projection for one voiceprint record."""

    voiceprint_id: str
    artifact_id: str
    subject_id: str
    revision: int
    lifecycle_state: str
    active: bool
    created_at: str
    updated_at: str
    model_name: str
    model_version: str
    schema_version: int
    lineage_root_id: str
    parent_voiceprint_id: str | None
    supersedes: str | None
    superseded_by: str | None


@dataclass(slots=True, frozen=True)
class VoiceprintRegistrySnapshot:
    """Safe, deterministic registry snapshot for diagnostics/telemetry."""

    records: tuple[VoiceprintRegistrySnapshotRecord, ...]


@dataclass(slots=True, frozen=True)
class VoiceprintRegistryHealth:
    """Registry health integration payload."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class VoiceprintRegistry:
    """Metadata registry layered above immutable storage artifact ids."""

    def __init__(
        self,
        *,
        store: Store[dict[str, Any]],
        storage_provider: VoiceprintStorageProvider,
    ) -> None:
        self._store = store
        self._storage_provider = storage_provider
        self._records: dict[str, VoiceprintRecord] = {}
        self._loaded = False
        self._cleared = False

    @classmethod
    async def create(
        cls,
        *,
        hass: HomeAssistant,
        storage_provider: VoiceprintStorageProvider,
    ) -> VoiceprintRegistry:
        """Create and load registry state from Home Assistant storage."""
        store: Store[dict[str, Any]] = Store(
            hass,
            VOICEPRINT_REGISTRY_STORE_VERSION,
            VOICEPRINT_REGISTRY_STORE_KEY,
        )
        registry = cls(store=store, storage_provider=storage_provider)
        await registry.async_load()
        return registry

    async def async_load(self) -> None:
        """Load persisted registry metadata from storage."""
        payload = await self._store.async_load()
        if payload is None:
            self._records = {}
            self._loaded = True
            return

        raw_records = payload.get("records", [])
        if not isinstance(raw_records, list):
            raise VoiceprintRegistryValidationError("voiceprint_record_invalid")

        loaded: dict[str, VoiceprintRecord] = {}
        for item in raw_records:
            record = _record_from_dict(item)
            loaded[record.voiceprint_id.value] = record

        self._records = loaded
        self._loaded = True

    async def register_record(self, record: VoiceprintRecord) -> VoiceprintRecord:
        """Register one immutable voiceprint metadata record."""
        self._ensure_loaded()
        _validate_record(record)

        existing = self._records.get(record.voiceprint_id.value)
        if existing is not None:
            if existing.artifact_id != record.artifact_id:
                raise VoiceprintRegistryArtifactMutationError("voiceprint_artifact_immutable")
            raise VoiceprintRegistryDuplicateError("voiceprint_duplicate_record")

        artifact_exists = await self._storage_provider.artifact_exists(record.artifact_id)
        if not artifact_exists:
            raise VoiceprintRegistryValidationError("voiceprint_artifact_missing")

        self._records[record.voiceprint_id.value] = record
        await self._persist()
        return record

    async def update_record(self, record: VoiceprintRecord) -> VoiceprintRecord:
        """Persist metadata updates for an existing record without changing artifact identity."""
        self._ensure_loaded()
        _validate_record(record)

        existing = self._records.get(record.voiceprint_id.value)
        if existing is None:
            raise VoiceprintRegistryRecordNotFoundError("voiceprint_registry_not_loaded")
        if existing.voiceprint_id != record.voiceprint_id:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_revision_identity_immutable")
        if existing.artifact_id != record.artifact_id:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_artifact_immutable")
        if existing.lineage.revision != record.lineage.revision:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_revision_identity_immutable")
        if existing.lineage.lineage_root_id != record.lineage.lineage_root_id:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_revision_identity_immutable")
        if existing.lineage.parent_voiceprint_id != record.lineage.parent_voiceprint_id:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_revision_identity_immutable")
        if existing.lineage.supersedes != record.lineage.supersedes:
            raise VoiceprintRegistryArtifactMutationError("voiceprint_revision_identity_immutable")

        self._records[record.voiceprint_id.value] = record
        await self._persist()
        return record

    def get_by_voiceprint_id(self, voiceprint_id: VoiceprintId) -> VoiceprintRecord:
        """Get one record by voiceprint id."""
        self._ensure_loaded()
        record = self._records.get(voiceprint_id.value)
        if record is None:
            raise VoiceprintRegistryRecordNotFoundError("voiceprint_registry_not_loaded")
        return record

    def get_by_artifact_id(self, artifact_id: VoiceprintArtifactId) -> VoiceprintRecord | None:
        """Get one record by immutable artifact id."""
        self._ensure_loaded()
        for record in self._records.values():
            if record.artifact_id == artifact_id:
                return record
        return None

    def get_by_subject_id(self, subject_id: VoiceprintSubjectId) -> tuple[VoiceprintRecord, ...]:
        """Get records indexed by subject id."""
        self._ensure_loaded()
        records = [record for record in self._records.values() if record.subject_id == subject_id]
        return tuple(sorted(records, key=lambda item: item.voiceprint_id.value))

    def get_by_lineage_root_id(self, lineage_root_id: VoiceprintId) -> tuple[VoiceprintRecord, ...]:
        """Get records indexed by lineage root id."""
        self._ensure_loaded()
        records = [
            record
            for record in self._records.values()
            if record.lineage.lineage_root_id == lineage_root_id
        ]
        return tuple(sorted(records, key=lambda item: item.voiceprint_id.value))

    def list_records(self) -> tuple[VoiceprintRecord, ...]:
        """List all records deterministically."""
        self._ensure_loaded()
        return tuple(self._records[key] for key in sorted(self._records))

    def list_active_records(self) -> tuple[VoiceprintRecord, ...]:
        """List records currently marked active."""
        self._ensure_loaded()
        return tuple(record for record in self.list_records() if record.active)

    def snapshot(self) -> VoiceprintRegistrySnapshot:
        """Return safe registry snapshot for future diagnostics/telemetry."""
        self._ensure_loaded()
        snapshot_records = tuple(_snapshot_record(record) for record in self.list_records())
        return VoiceprintRegistrySnapshot(records=snapshot_records)

    async def validate_health(self) -> VoiceprintRegistryHealth:
        """Validate registry readiness and safe artifact references."""
        if not self._loaded:
            return VoiceprintRegistryHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_registry_not_loaded",),
                details={"loaded": False, "record_count": 0},
            )

        for record in self.list_records():
            try:
                if not await self._storage_provider.artifact_exists(record.artifact_id):
                    return VoiceprintRegistryHealth(
                        state=HealthState.UNAVAILABLE,
                        reason_codes=("voiceprint_artifact_missing",),
                        details={"loaded": True, "record_count": len(self._records)},
                    )
            except VoiceIdentityStorageArtifactNotFoundError:
                return VoiceprintRegistryHealth(
                    state=HealthState.UNAVAILABLE,
                    reason_codes=("voiceprint_artifact_missing",),
                    details={"loaded": True, "record_count": len(self._records)},
                )

        return VoiceprintRegistryHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_registry_ready",),
            details={"loaded": True, "record_count": len(self._records)},
        )

    def clear(self) -> None:
        """Clear in-memory runtime state."""
        self._records = {}
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    async def _persist(self) -> None:
        payload = {"records": [_record_to_dict(record) for record in self.list_records()]}
        await self._store.async_save(payload)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise VoiceprintRegistryValidationError("voiceprint_registry_not_loaded")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_record(record: VoiceprintRecord) -> None:
    if record.lineage.revision < 1:
        raise VoiceprintRegistryValidationError("voiceprint_record_invalid")
    if record.lineage.lineage_root_id.value == "":
        raise VoiceprintRegistryValidationError("voiceprint_record_invalid")
    if record.active and record.lifecycle_state is VoiceprintLifecycleState.DELETED:
        raise VoiceprintRegistryValidationError("voiceprint_record_invalid")
    if not record.model_name.strip() or not record.model_version.strip():
        raise VoiceprintRegistryValidationError("voiceprint_record_invalid")
    if record.schema_version < 1:
        raise VoiceprintRegistryValidationError("voiceprint_record_invalid")


def create_voiceprint_record(
    *,
    voiceprint_id: str,
    artifact_id: str,
    subject_id: str,
    revision: int,
    lifecycle_state: VoiceprintLifecycleState,
    active: bool,
    model_name: str,
    model_version: str,
    schema_version: int,
    lineage_root_id: str | None = None,
    parent_voiceprint_id: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> VoiceprintRecord:
    """Create a validated voiceprint record from primitive inputs."""
    parsed_voiceprint_id = VoiceprintId.parse(voiceprint_id)
    parsed_artifact_id = VoiceprintArtifactId.parse(artifact_id)
    parsed_subject_id = VoiceprintSubjectId.parse(subject_id)
    parsed_root = VoiceprintId.parse(lineage_root_id or voiceprint_id)
    parsed_parent = VoiceprintId.parse(parent_voiceprint_id) if parent_voiceprint_id else None
    parsed_supersedes = VoiceprintId.parse(supersedes) if supersedes else None
    parsed_superseded_by = VoiceprintId.parse(superseded_by) if superseded_by else None

    timestamp = created_at or _utcnow_iso()
    record = VoiceprintRecord(
        voiceprint_id=parsed_voiceprint_id,
        artifact_id=parsed_artifact_id,
        subject_id=parsed_subject_id,
        lineage=VoiceprintLineage(
            revision=revision,
            lineage_root_id=parsed_root,
            parent_voiceprint_id=parsed_parent,
            supersedes=parsed_supersedes,
            superseded_by=parsed_superseded_by,
        ),
        lifecycle_state=lifecycle_state,
        active=active,
        created_at=timestamp,
        updated_at=updated_at or timestamp,
        model_name=model_name.strip(),
        model_version=model_version.strip(),
        schema_version=schema_version,
    )
    _validate_record(record)
    return record


def replace_voiceprint_record(
    record: VoiceprintRecord,
    *,
    lifecycle_state: VoiceprintLifecycleState | None = None,
    active: bool | None = None,
    supersedes: VoiceprintId | None | object = ...,
    superseded_by: VoiceprintId | None | object = ...,
    updated_at: str | None = None,
) -> VoiceprintRecord:
    """Return a validated copy of a record with metadata-only updates."""
    lineage = record.lineage

    if supersedes is not ...:
        lineage = replace(lineage, supersedes=supersedes)
    if superseded_by is not ...:
        lineage = replace(lineage, superseded_by=superseded_by)

    next_record = replace(
        record,
        lineage=lineage,
        lifecycle_state=lifecycle_state or record.lifecycle_state,
        active=record.active if active is None else active,
        updated_at=updated_at or _utcnow_iso(),
    )
    _validate_record(next_record)
    return next_record


def _record_to_dict(record: VoiceprintRecord) -> dict[str, Any]:
    return {
        "voiceprint_id": record.voiceprint_id.value,
        "artifact_id": record.artifact_id.value,
        "subject_id": record.subject_id.value,
        "revision": record.lineage.revision,
        "lineage_root_id": record.lineage.lineage_root_id.value,
        "parent_voiceprint_id": record.lineage.parent_voiceprint_id.value
        if record.lineage.parent_voiceprint_id
        else None,
        "supersedes": record.lineage.supersedes.value if record.lineage.supersedes else None,
        "superseded_by": record.lineage.superseded_by.value
        if record.lineage.superseded_by
        else None,
        "lifecycle_state": record.lifecycle_state.value,
        "active": record.active,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "model_name": record.model_name,
        "model_version": record.model_version,
        "schema_version": record.schema_version,
    }


def _record_from_dict(payload: dict[str, Any]) -> VoiceprintRecord:
    return create_voiceprint_record(
        voiceprint_id=str(payload["voiceprint_id"]),
        artifact_id=str(payload["artifact_id"]),
        subject_id=str(payload["subject_id"]),
        revision=int(payload["revision"]),
        lineage_root_id=str(payload["lineage_root_id"]),
        parent_voiceprint_id=str(payload["parent_voiceprint_id"])
        if payload.get("parent_voiceprint_id")
        else None,
        supersedes=str(payload["supersedes"]) if payload.get("supersedes") else None,
        superseded_by=str(payload["superseded_by"]) if payload.get("superseded_by") else None,
        lifecycle_state=VoiceprintLifecycleState(str(payload["lifecycle_state"])),
        active=bool(payload["active"]),
        created_at=str(payload["created_at"]),
        updated_at=str(payload["updated_at"]),
        model_name=str(payload["model_name"]),
        model_version=str(payload["model_version"]),
        schema_version=int(payload["schema_version"]),
    )


def _snapshot_record(record: VoiceprintRecord) -> VoiceprintRegistrySnapshotRecord:
    return VoiceprintRegistrySnapshotRecord(
        voiceprint_id=record.voiceprint_id.value,
        artifact_id=record.artifact_id.value,
        subject_id=record.subject_id.value,
        revision=record.lineage.revision,
        lifecycle_state=record.lifecycle_state.value,
        active=record.active,
        created_at=record.created_at,
        updated_at=record.updated_at,
        model_name=record.model_name,
        model_version=record.model_version,
        schema_version=record.schema_version,
        lineage_root_id=record.lineage.lineage_root_id.value,
        parent_voiceprint_id=record.lineage.parent_voiceprint_id.value
        if record.lineage.parent_voiceprint_id
        else None,
        supersedes=record.lineage.supersedes.value if record.lineage.supersedes else None,
        superseded_by=record.lineage.superseded_by.value if record.lineage.superseded_by else None,
    )
