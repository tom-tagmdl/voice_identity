"""Voiceprint status and metadata retrieval operations.

This module provides read-only public service operations that project safe
voiceprint status and metadata views for external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile

from .health_state import HealthState
from .voiceprint_lifecycle import VoiceprintLifecycleManager
from .voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRecord,
    VoiceprintRegistry,
    VoiceprintRegistryValidationError,
)
from .voiceprint_revision import VoiceprintRevisionManager

_CONTRACT_VERSION_CURRENT = 1
_CONTRACT_VERSION_MINIMUM_SUPPORTED = 1
_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class GetVoiceprintStatusFailureCategory(StrEnum):
    """Safe failure taxonomy for public status/metadata operations."""

    VOICEPRINT_NOT_FOUND = "voiceprint_not_found"
    METADATA_UNAVAILABLE = "metadata_unavailable"
    STATUS_UNAVAILABLE = "status_unavailable"
    CONTRACT_VERSION_UNSUPPORTED = "contract_version_unsupported"
    OPERATION_NOT_LOADED = "operation_not_loaded"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


class VoiceprintPublicLifecycleStatus(StrEnum):
    """Public lifecycle statuses exposed by VI-115."""

    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class GetVoiceprintStatusRequest:
    """Public status request contract."""

    voiceprint_id: str
    compatibility_version: int = _CONTRACT_VERSION_CURRENT
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        voiceprint_id: str,
        compatibility_version: int = _CONTRACT_VERSION_CURRENT,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> GetVoiceprintStatusRequest:
        return cls(
            voiceprint_id=voiceprint_id.strip(),
            compatibility_version=compatibility_version,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class GetVoiceprintMetadataRequest:
    """Public metadata request contract."""

    voiceprint_id: str
    compatibility_version: int = _CONTRACT_VERSION_CURRENT
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        voiceprint_id: str,
        compatibility_version: int = _CONTRACT_VERSION_CURRENT,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> GetVoiceprintMetadataRequest:
        return cls(
            voiceprint_id=voiceprint_id.strip(),
            compatibility_version=compatibility_version,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class VoiceprintPublicMetadata:
    """Approved safe metadata projection for public consumers."""

    metadata_contract_version: int
    compatibility_version: int
    voiceprint_id: str
    lifecycle_state: str
    active: bool
    revision: int
    revision_count: int
    superseded: bool
    created_timestamp: str
    updated_timestamp: str
    provider_identifier: str | None
    model_identifier: str | None
    representation_version: int | None
    quality_summary: str
    status_summary: str


@dataclass(slots=True, frozen=True)
class GetVoiceprintStatusSuccessResult:
    """Public success contract for status retrieval."""

    success: bool
    voiceprint_id: str
    lifecycle_status: str
    active: bool
    revision: int
    superseded: bool
    created_timestamp: str
    updated_timestamp: str
    status_summary: str
    compatibility_version: int
    safe_metadata: VoiceprintPublicMetadata
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class GetVoiceprintMetadataSuccessResult:
    """Public success contract for metadata retrieval."""

    success: bool
    voiceprint_id: str
    compatibility_version: int
    metadata: VoiceprintPublicMetadata
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class GetVoiceprintOperationFailureResult:
    """Public failure contract for status/metadata retrieval."""

    success: bool
    voiceprint_id: str
    failure_category: GetVoiceprintStatusFailureCategory
    reason_code: str
    compatibility_version: int
    diagnostics: dict[str, bool | int | float | str | None]
    completed_at: str


GetVoiceprintStatusResult = GetVoiceprintStatusSuccessResult | GetVoiceprintOperationFailureResult
GetVoiceprintMetadataResult = GetVoiceprintMetadataSuccessResult | GetVoiceprintOperationFailureResult


@dataclass(slots=True, frozen=True)
class GetVoiceprintStatusOperationHealth:
    """VI-115 health projection for integration health-engine."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class GetVoiceprintStatusOperation:
    """Read-only public status and metadata operation surface."""

    def __init__(
        self,
        *,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
        revision_manager: VoiceprintRevisionManager,
    ) -> None:
        self._registry = registry
        self._lifecycle_manager = lifecycle_manager
        self._revision_manager = revision_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
        revision_manager: VoiceprintRevisionManager,
    ) -> GetVoiceprintStatusOperation:
        return cls(
            registry=registry,
            lifecycle_manager=lifecycle_manager,
            revision_manager=revision_manager,
        )

    async def execute(self, request: GetVoiceprintStatusRequest) -> GetVoiceprintStatusResult:
        if not self._loaded:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": False},
            )

        if not _is_supported_contract_version(request.compatibility_version):
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.CONTRACT_VERSION_UNSUPPORTED,
                reason_code="contract_version_unsupported",
                compatibility_version=request.compatibility_version,
                diagnostics={
                    "loaded": True,
                    "requested_contract_version": request.compatibility_version,
                    "supported_contract_version": _CONTRACT_VERSION_CURRENT,
                },
            )

        try:
            record = self._get_record(request.voiceprint_id)
            if record is None:
                return self._build_failure(
                    request_voiceprint_id=request.voiceprint_id,
                    failure_category=GetVoiceprintStatusFailureCategory.VOICEPRINT_NOT_FOUND,
                    reason_code="voiceprint_not_found",
                    compatibility_version=request.compatibility_version,
                    diagnostics={"loaded": True},
                )

            revision_count = self._revision_count(record)
            lifecycle_status = _public_lifecycle_status(record.lifecycle_state)
            status_summary = _status_summary(lifecycle_status)
            metadata = _project_public_metadata(
                record=record,
                lifecycle_status=lifecycle_status,
                status_summary=status_summary,
                revision_count=revision_count,
                compatibility_version=request.compatibility_version,
            )

            return GetVoiceprintStatusSuccessResult(
                success=True,
                voiceprint_id=record.voiceprint_id.value,
                lifecycle_status=lifecycle_status.value,
                active=record.active,
                revision=record.lineage.revision,
                superseded=record.lineage.superseded_by is not None,
                created_timestamp=record.created_at,
                updated_timestamp=record.updated_at,
                status_summary=status_summary,
                compatibility_version=request.compatibility_version,
                safe_metadata=metadata,
                diagnostics={
                    "loaded": True,
                    "revision_count": revision_count,
                    "metadata_contract_version": _CONTRACT_VERSION_CURRENT,
                },
            )
        except VoiceprintRegistryValidationError:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.STATUS_UNAVAILABLE,
                reason_code="status_unavailable",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": True},
            )
        except Exception:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def get_metadata(self, request: GetVoiceprintMetadataRequest) -> GetVoiceprintMetadataResult:
        if not self._loaded:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": False},
            )

        if not _is_supported_contract_version(request.compatibility_version):
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.CONTRACT_VERSION_UNSUPPORTED,
                reason_code="contract_version_unsupported",
                compatibility_version=request.compatibility_version,
                diagnostics={
                    "loaded": True,
                    "requested_contract_version": request.compatibility_version,
                    "supported_contract_version": _CONTRACT_VERSION_CURRENT,
                },
            )

        try:
            record = self._get_record(request.voiceprint_id)
            if record is None:
                return self._build_failure(
                    request_voiceprint_id=request.voiceprint_id,
                    failure_category=GetVoiceprintStatusFailureCategory.VOICEPRINT_NOT_FOUND,
                    reason_code="voiceprint_not_found",
                    compatibility_version=request.compatibility_version,
                    diagnostics={"loaded": True},
                )

            revision_count = self._revision_count(record)
            lifecycle_status = _public_lifecycle_status(record.lifecycle_state)
            status_summary = _status_summary(lifecycle_status)
            metadata = _project_public_metadata(
                record=record,
                lifecycle_status=lifecycle_status,
                status_summary=status_summary,
                revision_count=revision_count,
                compatibility_version=request.compatibility_version,
            )

            return GetVoiceprintMetadataSuccessResult(
                success=True,
                voiceprint_id=record.voiceprint_id.value,
                compatibility_version=request.compatibility_version,
                metadata=metadata,
                diagnostics={
                    "loaded": True,
                    "revision_count": revision_count,
                    "metadata_contract_version": _CONTRACT_VERSION_CURRENT,
                },
            )
        except VoiceprintRegistryValidationError:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE,
                reason_code="metadata_unavailable",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": True},
            )
        except Exception:
            return self._build_failure(
                request_voiceprint_id=request.voiceprint_id,
                failure_category=GetVoiceprintStatusFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                compatibility_version=request.compatibility_version,
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def validate_health(self) -> GetVoiceprintStatusOperationHealth:
        if not self._loaded:
            return GetVoiceprintStatusOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_not_loaded",),
                details={"loaded": False},
            )

        try:
            registry_health = await self._registry.validate_health()
            lifecycle_health = await self._lifecycle_manager.validate_health()
            revision_health = await self._revision_manager.validate_health()
        except Exception:
            return GetVoiceprintStatusOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_internal_error",),
                details={"loaded": True},
            )

        if registry_health.state is not HealthState.HEALTHY:
            return GetVoiceprintStatusOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("status_unavailable",),
                details={"loaded": True},
            )

        if lifecycle_health.state is not HealthState.HEALTHY:
            return GetVoiceprintStatusOperationHealth(
                state=HealthState.DEGRADED,
                reason_codes=("status_unavailable",),
                details={"loaded": True},
            )

        if revision_health.state is not HealthState.HEALTHY:
            return GetVoiceprintStatusOperationHealth(
                state=HealthState.DEGRADED,
                reason_codes=("metadata_unavailable",),
                details={"loaded": True},
            )

        return GetVoiceprintStatusOperationHealth(
            state=HealthState.HEALTHY,
            reason_codes=("get_voiceprint_status_ready",),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _get_record(self, voiceprint_id: str) -> VoiceprintRecord | None:
        try:
            parsed = VoiceprintId.parse(voiceprint_id)
        except Exception:
            return None
        for record in self._registry.list_records():
            if record.voiceprint_id == parsed:
                return record
        return None

    def _revision_count(self, record: VoiceprintRecord) -> int:
        chain = self._revision_manager.traverse_lineage(record.lineage.lineage_root_id)
        return len(chain)

    def _build_failure(
        self,
        *,
        request_voiceprint_id: str,
        failure_category: GetVoiceprintStatusFailureCategory,
        reason_code: str,
        compatibility_version: int,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> GetVoiceprintOperationFailureResult:
        return GetVoiceprintOperationFailureResult(
            success=False,
            voiceprint_id=request_voiceprint_id,
            failure_category=failure_category,
            reason_code=_safe_token(reason_code, failure_category.value) or failure_category.value,
            compatibility_version=compatibility_version,
            diagnostics=_sanitize_metadata(diagnostics),
            completed_at=_utcnow_iso(),
        )


def _project_public_metadata(
    *,
    record: VoiceprintRecord,
    lifecycle_status: VoiceprintPublicLifecycleStatus,
    status_summary: str,
    revision_count: int,
    compatibility_version: int,
) -> VoiceprintPublicMetadata:
    model_identifier = _safe_token(f"{record.model_name}:{record.model_version}", None)
    return VoiceprintPublicMetadata(
        metadata_contract_version=_CONTRACT_VERSION_CURRENT,
        compatibility_version=compatibility_version,
        voiceprint_id=record.voiceprint_id.value,
        lifecycle_state=lifecycle_status.value,
        active=record.active,
        revision=record.lineage.revision,
        revision_count=revision_count,
        superseded=record.lineage.superseded_by is not None,
        created_timestamp=record.created_at,
        updated_timestamp=record.updated_at,
        provider_identifier="voice_identity",
        model_identifier=model_identifier,
        representation_version=record.schema_version,
        quality_summary="quality_summary_unavailable",
        status_summary=status_summary,
    )


def _public_lifecycle_status(state: VoiceprintLifecycleState) -> VoiceprintPublicLifecycleStatus:
    if state is VoiceprintLifecycleState.PENDING:
        return VoiceprintPublicLifecycleStatus.PENDING
    if state is VoiceprintLifecycleState.ACTIVE:
        return VoiceprintPublicLifecycleStatus.ACTIVE
    if state is VoiceprintLifecycleState.INACTIVE:
        return VoiceprintPublicLifecycleStatus.INACTIVE
    if state is VoiceprintLifecycleState.SUPERSEDED:
        return VoiceprintPublicLifecycleStatus.SUPERSEDED
    if state is VoiceprintLifecycleState.DELETED:
        return VoiceprintPublicLifecycleStatus.RETIRED
    if state is VoiceprintLifecycleState.FAILED:
        return VoiceprintPublicLifecycleStatus.FAILED
    return VoiceprintPublicLifecycleStatus.UNKNOWN


def _status_summary(lifecycle_status: VoiceprintPublicLifecycleStatus) -> str:
    mapping = {
        VoiceprintPublicLifecycleStatus.PENDING: "voiceprint_pending",
        VoiceprintPublicLifecycleStatus.ACTIVE: "voiceprint_active",
        VoiceprintPublicLifecycleStatus.INACTIVE: "voiceprint_inactive",
        VoiceprintPublicLifecycleStatus.SUPERSEDED: "voiceprint_superseded",
        VoiceprintPublicLifecycleStatus.RETIRED: "voiceprint_retired",
        VoiceprintPublicLifecycleStatus.FAILED: "voiceprint_failed",
        VoiceprintPublicLifecycleStatus.UNKNOWN: "voiceprint_unknown",
    }
    return mapping[lifecycle_status]


def _is_supported_contract_version(version: int) -> bool:
    return _CONTRACT_VERSION_MINIMUM_SUPPORTED <= version <= _CONTRACT_VERSION_CURRENT


def _sanitize_metadata(
    values: dict[str, bool | int | float | str | None],
) -> dict[str, bool | int | float | str | None]:
    sanitized: dict[str, bool | int | float | str | None] = {}
    for key, value in values.items():
        safe_key = _safe_token(key, "meta")
        if _is_sensitive_key(safe_key):
            continue
        if isinstance(value, str):
            safe_value = _safe_metadata_value(value)
            if safe_value:
                sanitized[safe_key] = safe_value
        elif isinstance(value, (bool, int, float, type(None))):
            sanitized[safe_key] = value
    return sanitized


def _safe_token(value: str | None, fallback: str | None) -> str | None:
    if value is not None:
        normalized = value.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
            return normalized
    if fallback is not None:
        normalized_fallback = fallback.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized_fallback):
            return normalized_fallback
    return None


def _safe_metadata_value(value: str) -> str:
    normalized = _safe_token(value, "")
    if not normalized:
        return ""
    if "http" in normalized or "/" in normalized or "\\" in normalized:
        return ""
    if "token" in normalized or "secret" in normalized or "key" in normalized:
        return ""
    if "traceback" in normalized or "exception" in normalized:
        return ""
    return normalized


def _is_sensitive_key(key: str) -> bool:
    return any(token in key for token in ("token", "secret", "key", "path", "url", "payload", "embedding"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
