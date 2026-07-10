"""Artifact persistence engine for durable voiceprint artifacts.

This layer orchestrates persistence workflows across storage, registry,
lifecycle, and revision managers while preserving privacy boundaries.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
from re import compile as re_compile

from .health_state import HealthState
from .storage_provider import (
    VoiceIdentityStorageArtifactNotFoundError,
    VoiceIdentityStorageDeleteError,
    VoiceIdentityStorageReadError,
    VoiceIdentityStorageWriteError,
    VoiceprintStorageProvider,
)
from .voiceprint_lifecycle import (
    VoiceprintLifecycleError,
    VoiceprintLifecycleManager,
)
from .voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRecord,
    VoiceprintRegistry,
    VoiceprintRegistryError,
    VoiceprintSubjectId,
)
from .voiceprint_revision import (
    VoiceprintRevisionError,
    VoiceprintRevisionManager,
)

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class ArtifactPersistenceError(Exception):
    """Base exception for artifact persistence workflows."""


class ArtifactPersistencePayloadError(ArtifactPersistenceError):
    """Raised when encrypted payload contracts are invalid."""


class ArtifactPersistenceStorageError(ArtifactPersistenceError):
    """Raised when storage orchestration fails."""


class ArtifactPersistenceRegistryError(ArtifactPersistenceError):
    """Raised when registry orchestration fails."""


class ArtifactPersistenceLifecycleError(ArtifactPersistenceError):
    """Raised when lifecycle orchestration fails."""


class ArtifactPersistenceRevisionError(ArtifactPersistenceError):
    """Raised when revision orchestration fails."""


@dataclass(slots=True, frozen=True)
class IntegrityMetadata:
    """Safe integrity metadata generated at persist time."""

    digest_algorithm: str
    digest_hex: str
    payload_size: int
    payload_format_version: int
    created_at: str
    metadata_schema_version: int = 1


@dataclass(slots=True, frozen=True)
class EncryptedRepresentationEnvelope:
    """Encrypted durable representation envelope stored as artifact bytes."""

    encrypted: bool
    payload_format_version: int
    encryption_scheme: str
    key_reference: str | None
    model_name: str
    model_version: str
    schema_version: int
    integrity: IntegrityMetadata
    encrypted_payload: bytes


@dataclass(slots=True, frozen=True)
class PersistArtifactRequest:
    """Persistence request for a final durable voiceprint artifact."""

    voiceprint_id: str
    artifact_id: str
    subject_id: str | None
    current_voiceprint_id: str | None
    encrypted: bool
    encrypted_payload: bytes
    payload_format_version: int
    encryption_scheme: str
    key_reference: str | None
    model_name: str
    model_version: str
    schema_version: int
    activate: bool = True


@dataclass(slots=True, frozen=True)
class PersistArtifactResult:
    """Safe result for a persistence workflow."""

    voiceprint_id: str
    artifact_id: str
    revision: int
    lineage_root_id: str
    lifecycle_state: str
    active: bool
    integrity: IntegrityMetadata


@dataclass(slots=True, frozen=True)
class LoadArtifactResult:
    """Safe load result for a durable artifact."""

    voiceprint_id: str
    artifact_id: str
    subject_id: str
    revision: int
    lifecycle_state: str
    active: bool
    envelope: EncryptedRepresentationEnvelope


@dataclass(slots=True, frozen=True)
class DeleteArtifactResult:
    """Safe delete result for metadata plus artifact bytes coordination."""

    voiceprint_id: str
    artifact_id: str
    lifecycle_state: str
    artifact_deleted: bool


@dataclass(slots=True, frozen=True)
class ArtifactPersistenceHealth:
    """Persistence engine health integration payload."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class ArtifactPersistenceEngine:
    """Coordinates final artifact persistence workflows across lower layers."""

    def __init__(
        self,
        *,
        storage_provider: VoiceprintStorageProvider,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
        revision_manager: VoiceprintRevisionManager,
    ) -> None:
        self._storage_provider = storage_provider
        self._registry = registry
        self._lifecycle_manager = lifecycle_manager
        self._revision_manager = revision_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        storage_provider: VoiceprintStorageProvider,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
        revision_manager: VoiceprintRevisionManager,
    ) -> ArtifactPersistenceEngine:
        return cls(
            storage_provider=storage_provider,
            registry=registry,
            lifecycle_manager=lifecycle_manager,
            revision_manager=revision_manager,
        )

    async def persist_artifact(self, request: PersistArtifactRequest) -> PersistArtifactResult:
        """Persist a final encrypted voiceprint artifact and coordinate metadata."""
        self._ensure_loaded()
        envelope = _build_envelope(request)
        serialized = _serialize_envelope(envelope)

        try:
            if request.current_voiceprint_id is None:
                if request.subject_id is None:
                    raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid")
                record = self._revision_manager.prepare_initial_record(
                    voiceprint_id=request.voiceprint_id,
                    artifact_id=request.artifact_id,
                    subject_id=request.subject_id,
                    model_name=request.model_name,
                    model_version=request.model_version,
                    schema_version=request.schema_version,
                    lifecycle_state=VoiceprintLifecycleState.PENDING,
                    active=False,
                )
            else:
                record = self._revision_manager.prepare_next_revision_record(
                    current_voiceprint_id=VoiceprintId.parse(request.current_voiceprint_id),
                    new_voiceprint_id=request.voiceprint_id,
                    new_artifact_id=request.artifact_id,
                    model_name=request.model_name,
                    model_version=request.model_version,
                    schema_version=request.schema_version,
                    lifecycle_state=VoiceprintLifecycleState.PENDING,
                    active=False,
                )
        except (VoiceprintRevisionError, VoiceprintRegistryError) as err:
            raise ArtifactPersistenceRevisionError("artifact_persistence_revision_failed") from err

        try:
            if await self._storage_provider.artifact_exists(record.artifact_id):
                raise ArtifactPersistenceStorageError("artifact_persistence_save_failed")
            await self._storage_provider.save_artifact(record.artifact_id, serialized)
        except VoiceIdentityStorageWriteError as err:
            raise ArtifactPersistenceStorageError("artifact_persistence_save_failed") from err

        try:
            saved_record = await self._registry.register_record(record)
        except VoiceprintRegistryError as err:
            await self._cleanup_saved_artifact(record)
            raise ArtifactPersistenceRegistryError("artifact_persistence_registry_failed") from err

        try:
            if request.activate:
                if request.current_voiceprint_id is None:
                    saved_record = await self._lifecycle_manager.activate_record(saved_record.voiceprint_id)
                else:
                    _, saved_record = await self._revision_manager.coordinate_supersession(
                        current_voiceprint_id=VoiceprintId.parse(request.current_voiceprint_id),
                        replacement_voiceprint_id=saved_record.voiceprint_id,
                    )
        except (VoiceprintLifecycleError, VoiceprintRevisionError) as err:
            raise ArtifactPersistenceLifecycleError("artifact_persistence_lifecycle_failed") from err

        return PersistArtifactResult(
            voiceprint_id=saved_record.voiceprint_id.value,
            artifact_id=saved_record.artifact_id.value,
            revision=saved_record.lineage.revision,
            lineage_root_id=saved_record.lineage.lineage_root_id.value,
            lifecycle_state=saved_record.lifecycle_state.value,
            active=saved_record.active,
            integrity=envelope.integrity,
        )

    async def load_artifact(self, voiceprint_id: VoiceprintId) -> LoadArtifactResult:
        """Load one persisted encrypted artifact through registry plus storage provider."""
        self._ensure_loaded()
        try:
            record = self._registry.get_by_voiceprint_id(voiceprint_id)
            payload = await self._storage_provider.load_artifact(record.artifact_id)
            envelope = _deserialize_envelope(payload)
        except VoiceprintRegistryError as err:
            raise ArtifactPersistenceRegistryError("artifact_persistence_load_failed") from err
        except (VoiceIdentityStorageArtifactNotFoundError, VoiceIdentityStorageReadError) as err:
            raise ArtifactPersistenceStorageError("artifact_persistence_load_failed") from err
        except ArtifactPersistencePayloadError as err:
            raise ArtifactPersistencePayloadError(str(err)) from err

        return LoadArtifactResult(
            voiceprint_id=record.voiceprint_id.value,
            artifact_id=record.artifact_id.value,
            subject_id=record.subject_id.value,
            revision=record.lineage.revision,
            lifecycle_state=record.lifecycle_state.value,
            active=record.active,
            envelope=envelope,
        )

    async def delete_artifact(self, voiceprint_id: VoiceprintId) -> DeleteArtifactResult:
        """Coordinate metadata deletion semantics and artifact byte deletion."""
        self._ensure_loaded()
        try:
            record = self._registry.get_by_voiceprint_id(voiceprint_id)
            deleted_record = await self._lifecycle_manager.delete_record(voiceprint_id)
        except VoiceprintRegistryError as err:
            raise ArtifactPersistenceRegistryError("artifact_persistence_delete_failed") from err
        except VoiceprintLifecycleError as err:
            raise ArtifactPersistenceLifecycleError("artifact_persistence_delete_failed") from err

        try:
            artifact_deleted = await self._storage_provider.delete_artifact(record.artifact_id)
        except VoiceIdentityStorageDeleteError as err:
            raise ArtifactPersistenceStorageError("artifact_persistence_delete_failed") from err

        return DeleteArtifactResult(
            voiceprint_id=deleted_record.voiceprint_id.value,
            artifact_id=deleted_record.artifact_id.value,
            lifecycle_state=deleted_record.lifecycle_state.value,
            artifact_deleted=artifact_deleted,
        )

    async def validate_health(self) -> ArtifactPersistenceHealth:
        """Validate persistence engine readiness across dependencies."""
        if not self._loaded:
            return ArtifactPersistenceHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_persistence_not_loaded",),
                details={"loaded": False},
            )

        storage_health = await self._storage_provider.validate_availability()
        if storage_health.state is not HealthState.HEALTHY:
            return ArtifactPersistenceHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_persistence_save_failed",),
                details={"loaded": True},
            )

        registry_health = await self._registry.validate_health()
        if registry_health.state is not HealthState.HEALTHY:
            return ArtifactPersistenceHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_persistence_registry_failed",),
                details={"loaded": True},
            )

        lifecycle_health = await self._lifecycle_manager.validate_health()
        if lifecycle_health.state is not HealthState.HEALTHY:
            return ArtifactPersistenceHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_persistence_lifecycle_failed",),
                details={"loaded": True},
            )

        revision_health = await self._revision_manager.validate_health()
        if revision_health.state is not HealthState.HEALTHY:
            return ArtifactPersistenceHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_persistence_revision_failed",),
                details={"loaded": True},
            )

        return ArtifactPersistenceHealth(
            state=HealthState.HEALTHY,
            reason_codes=("artifact_persistence_ready",),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    async def _cleanup_saved_artifact(self, record: VoiceprintRecord) -> None:
        try:
            await self._storage_provider.delete_artifact(record.artifact_id)
        except Exception:
            return

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise ArtifactPersistenceError("artifact_persistence_not_loaded")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or not _SAFE_TOKEN_PATTERN.fullmatch(normalized):
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid")
    return normalized


def _build_envelope(request: PersistArtifactRequest) -> EncryptedRepresentationEnvelope:
    if not request.encrypted:
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_not_encrypted")
    if not request.encrypted_payload:
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid")
    if request.payload_format_version < 1:
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid")

    integrity = IntegrityMetadata(
        digest_algorithm="sha256",
        digest_hex=hashlib.sha256(request.encrypted_payload).hexdigest(),
        payload_size=len(request.encrypted_payload),
        payload_format_version=request.payload_format_version,
        created_at=_utcnow_iso(),
    )
    return EncryptedRepresentationEnvelope(
        encrypted=True,
        payload_format_version=request.payload_format_version,
        encryption_scheme=_safe_token(request.encryption_scheme),
        key_reference=_safe_token(request.key_reference) if request.key_reference else None,
        model_name=_safe_token(request.model_name),
        model_version=_safe_token(request.model_version),
        schema_version=request.schema_version,
        integrity=integrity,
        encrypted_payload=request.encrypted_payload,
    )


def _serialize_envelope(envelope: EncryptedRepresentationEnvelope) -> bytes:
    payload = {
        "encrypted": envelope.encrypted,
        "payload_format_version": envelope.payload_format_version,
        "encryption_scheme": envelope.encryption_scheme,
        "key_reference": envelope.key_reference,
        "model_name": envelope.model_name,
        "model_version": envelope.model_version,
        "schema_version": envelope.schema_version,
        "integrity": asdict(envelope.integrity),
        "encrypted_payload_b64": base64.b64encode(envelope.encrypted_payload).decode("ascii"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _deserialize_envelope(serialized: bytes) -> EncryptedRepresentationEnvelope:
    try:
        payload = json.loads(serialized.decode("utf-8"))
    except Exception as err:
        raise ArtifactPersistencePayloadError("artifact_persistence_load_failed") from err

    if payload.get("encrypted") is not True:
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_not_encrypted")

    encrypted_payload_b64 = payload.get("encrypted_payload_b64")
    if not isinstance(encrypted_payload_b64, str):
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid")

    try:
        encrypted_payload = base64.b64decode(encrypted_payload_b64.encode("ascii"), validate=True)
    except Exception as err:
        raise ArtifactPersistencePayloadError("artifact_persistence_payload_invalid") from err

    integrity_payload = payload.get("integrity")
    if not isinstance(integrity_payload, dict):
        raise ArtifactPersistencePayloadError("artifact_persistence_integrity_metadata_failed")

    integrity = IntegrityMetadata(
        digest_algorithm=_safe_token(str(integrity_payload.get("digest_algorithm", ""))),
        digest_hex=_safe_token(str(integrity_payload.get("digest_hex", ""))),
        payload_size=int(integrity_payload.get("payload_size", 0)),
        payload_format_version=int(integrity_payload.get("payload_format_version", 0)),
        created_at=str(integrity_payload.get("created_at", "")),
        metadata_schema_version=int(integrity_payload.get("metadata_schema_version", 1)),
    )

    calculated_digest = hashlib.sha256(encrypted_payload).hexdigest()
    if calculated_digest != integrity.digest_hex:
        raise ArtifactPersistencePayloadError("artifact_persistence_integrity_metadata_failed")

    return EncryptedRepresentationEnvelope(
        encrypted=True,
        payload_format_version=int(payload.get("payload_format_version", 0)),
        encryption_scheme=_safe_token(str(payload.get("encryption_scheme", ""))),
        key_reference=_safe_token(str(payload.get("key_reference")))
        if payload.get("key_reference")
        else None,
        model_name=_safe_token(str(payload.get("model_name", ""))),
        model_version=_safe_token(str(payload.get("model_version", ""))),
        schema_version=int(payload.get("schema_version", 0)),
        integrity=integrity,
        encrypted_payload=encrypted_payload,
    )
