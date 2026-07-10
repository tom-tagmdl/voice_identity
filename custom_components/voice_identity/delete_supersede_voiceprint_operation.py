"""Delete and supersede voiceprint service operations.

This module provides read-only service-layer orchestration contracts that expose
public delete and supersede operations while delegating lifecycle and revision
authority to existing subsystem managers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile
from uuid import uuid4

from .health_state import HealthState
from .voiceprint_lifecycle import (
    VoiceprintLifecycleConflictError,
    VoiceprintLifecycleInvalidTransitionError,
    VoiceprintLifecycleManager,
    VoiceprintLifecycleNotLoadedError,
    VoiceprintLifecycleSupersessionError,
)
from .voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRecord,
    VoiceprintRegistry,
    VoiceprintRegistryValidationError,
)
from .voiceprint_revision import (
    VoiceprintRevisionConflictError,
    VoiceprintRevisionManager,
    VoiceprintRevisionNotLoadedError,
    VoiceprintRevisionValidationError,
)

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class VoiceprintOperationStatus(StrEnum):
    """Operation-level status progression."""

    REQUESTED = "requested"
    COMPLETED = "completed"
    FAILED = "failed"


class DeleteSupersedeFailureCategory(StrEnum):
    """Safe failure taxonomy for delete and supersede operations."""

    VOICEPRINT_NOT_FOUND = "voiceprint_not_found"
    VOICEPRINT_ALREADY_RETIRED = "voiceprint_already_retired"
    VOICEPRINT_NOT_ACTIVE = "voiceprint_not_active"
    SUPERSEDE_INVALID = "supersede_invalid"
    REVISION_CONFLICT = "revision_conflict"
    LIFECYCLE_TRANSITION_INVALID = "lifecycle_transition_invalid"
    OPERATION_NOT_LOADED = "operation_not_loaded"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


@dataclass(slots=True, frozen=True)
class DeleteVoiceprintRequest:
    """Public request contract for delete voiceprint operation."""

    voiceprint_id: str
    correlation_id: str | None = None
    reason: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        voiceprint_id: str,
        correlation_id: str | None = None,
        reason: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> DeleteVoiceprintRequest:
        return cls(
            voiceprint_id=voiceprint_id.strip(),
            correlation_id=_safe_token(correlation_id, None),
            reason=_safe_token(reason, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class SupersedeVoiceprintRequest:
    """Public request contract for supersede voiceprint operation."""

    existing_voiceprint_id: str
    new_voiceprint_id: str
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        existing_voiceprint_id: str,
        new_voiceprint_id: str,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> SupersedeVoiceprintRequest:
        return cls(
            existing_voiceprint_id=existing_voiceprint_id.strip(),
            new_voiceprint_id=new_voiceprint_id.strip(),
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class DeleteVoiceprintSuccessResult:
    """Public success contract for delete voiceprint operation."""

    success: bool
    operation_id: str
    voiceprint_id: str
    lifecycle_status: str
    operation_status: VoiceprintOperationStatus
    operation_timestamp: str
    safe_diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class SupersedeLifecycleChanges:
    """Public lifecycle transition projection for supersede operation."""

    previous_voiceprint_id: str
    previous_lifecycle_status: str
    active_voiceprint_id: str
    active_lifecycle_status: str


@dataclass(slots=True, frozen=True)
class SupersedeRevisionInformation:
    """Public revision lineage projection for supersede operation."""

    lineage_root_id: str
    previous_revision: int
    active_revision: int


@dataclass(slots=True, frozen=True)
class SupersedeVoiceprintSuccessResult:
    """Public success contract for supersede voiceprint operation."""

    success: bool
    operation_id: str
    previous_voiceprint_id: str
    active_voiceprint_id: str
    lifecycle_changes: SupersedeLifecycleChanges
    revision_information: SupersedeRevisionInformation
    status: VoiceprintOperationStatus
    operation_timestamp: str
    safe_diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class DeleteSupersedeFailureResult:
    """Public failure contract for delete/supersede operations."""

    success: bool
    operation_id: str
    operation_status: VoiceprintOperationStatus
    failure_category: DeleteSupersedeFailureCategory
    reason_code: str
    voiceprint_id: str | None
    previous_voiceprint_id: str | None
    active_voiceprint_id: str | None
    operation_timestamp: str
    safe_diagnostics: dict[str, bool | int | float | str | None]


DeleteVoiceprintResult = DeleteVoiceprintSuccessResult | DeleteSupersedeFailureResult
SupersedeVoiceprintResult = SupersedeVoiceprintSuccessResult | DeleteSupersedeFailureResult


@dataclass(slots=True, frozen=True)
class DeleteSupersedeOperationHealth:
    """Health projection for delete/supersede readiness."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class DeleteSupersedeVoiceprintOperation:
    """Service operation facade for delete and supersede actions."""

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
    ) -> DeleteSupersedeVoiceprintOperation:
        return cls(
            registry=registry,
            lifecycle_manager=lifecycle_manager,
            revision_manager=revision_manager,
        )

    async def delete_voiceprint(self, request: DeleteVoiceprintRequest) -> DeleteVoiceprintResult:
        operation_id = _operation_id()
        if not self._loaded:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": False},
            )

        record = self._find_record(request.voiceprint_id)
        if record is None:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.VOICEPRINT_NOT_FOUND,
                reason_code="voiceprint_not_found",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": True},
            )

        if record.lifecycle_state is VoiceprintLifecycleState.DELETED:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.VOICEPRINT_ALREADY_RETIRED,
                reason_code="voiceprint_already_retired",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": True, "lifecycle_status": "deleted"},
            )

        try:
            updated = await self._lifecycle_manager.delete_record(record.voiceprint_id)
            return DeleteVoiceprintSuccessResult(
                success=True,
                operation_id=operation_id,
                voiceprint_id=updated.voiceprint_id.value,
                lifecycle_status=updated.lifecycle_state.value,
                operation_status=VoiceprintOperationStatus.COMPLETED,
                operation_timestamp=_utcnow_iso(),
                safe_diagnostics={
                    "loaded": True,
                    "active": updated.active,
                    "revision": updated.lineage.revision,
                },
            )
        except VoiceprintLifecycleInvalidTransitionError:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.LIFECYCLE_TRANSITION_INVALID,
                reason_code="lifecycle_transition_invalid",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": True},
            )
        except VoiceprintLifecycleNotLoadedError:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": False},
            )
        except Exception:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                voiceprint_id=request.voiceprint_id,
                previous_voiceprint_id=None,
                active_voiceprint_id=None,
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def supersede_voiceprint(self, request: SupersedeVoiceprintRequest) -> SupersedeVoiceprintResult:
        operation_id = _operation_id()
        if not self._loaded:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": False},
            )

        if request.existing_voiceprint_id == request.new_voiceprint_id:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.SUPERSEDE_INVALID,
                reason_code="supersede_invalid",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )

        current = self._find_record(request.existing_voiceprint_id)
        replacement = self._find_record(request.new_voiceprint_id)
        if current is None or replacement is None:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.VOICEPRINT_NOT_FOUND,
                reason_code="voiceprint_not_found",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )

        if current.lifecycle_state is not VoiceprintLifecycleState.ACTIVE or not current.active:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.VOICEPRINT_NOT_ACTIVE,
                reason_code="voiceprint_not_active",
                voiceprint_id=current.voiceprint_id.value,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )

        if replacement.lifecycle_state not in {
            VoiceprintLifecycleState.PENDING,
            VoiceprintLifecycleState.INACTIVE,
        }:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.SUPERSEDE_INVALID,
                reason_code="supersede_invalid",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )

        try:
            previous_record, active_record = await self._revision_manager.coordinate_supersession(
                current_voiceprint_id=current.voiceprint_id,
                replacement_voiceprint_id=replacement.voiceprint_id,
            )
            return SupersedeVoiceprintSuccessResult(
                success=True,
                operation_id=operation_id,
                previous_voiceprint_id=previous_record.voiceprint_id.value,
                active_voiceprint_id=active_record.voiceprint_id.value,
                lifecycle_changes=SupersedeLifecycleChanges(
                    previous_voiceprint_id=previous_record.voiceprint_id.value,
                    previous_lifecycle_status=previous_record.lifecycle_state.value,
                    active_voiceprint_id=active_record.voiceprint_id.value,
                    active_lifecycle_status=active_record.lifecycle_state.value,
                ),
                revision_information=SupersedeRevisionInformation(
                    lineage_root_id=active_record.lineage.lineage_root_id.value,
                    previous_revision=previous_record.lineage.revision,
                    active_revision=active_record.lineage.revision,
                ),
                status=VoiceprintOperationStatus.COMPLETED,
                operation_timestamp=_utcnow_iso(),
                safe_diagnostics={
                    "loaded": True,
                    "previous_active": previous_record.active,
                    "active_active": active_record.active,
                },
            )
        except (VoiceprintRevisionConflictError, VoiceprintRevisionValidationError):
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.REVISION_CONFLICT,
                reason_code="revision_conflict",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )
        except VoiceprintLifecycleSupersessionError:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.SUPERSEDE_INVALID,
                reason_code="supersede_invalid",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )
        except (VoiceprintLifecycleInvalidTransitionError, VoiceprintLifecycleConflictError):
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.LIFECYCLE_TRANSITION_INVALID,
                reason_code="lifecycle_transition_invalid",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True},
            )
        except (VoiceprintRevisionNotLoadedError, VoiceprintLifecycleNotLoadedError):
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": False},
            )
        except Exception:
            return self._failure(
                operation_id=operation_id,
                failure_category=DeleteSupersedeFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                voiceprint_id=None,
                previous_voiceprint_id=request.existing_voiceprint_id,
                active_voiceprint_id=request.new_voiceprint_id,
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def validate_health(self) -> DeleteSupersedeOperationHealth:
        if not self._loaded:
            return DeleteSupersedeOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_not_loaded",),
                details={"loaded": False},
            )

        try:
            lifecycle_health = await self._lifecycle_manager.validate_health()
            revision_health = await self._revision_manager.validate_health()
            registry_health = await self._registry.validate_health()
        except Exception:
            return DeleteSupersedeOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_internal_error",),
                details={"loaded": True},
            )

        if lifecycle_health.state is not HealthState.HEALTHY:
            return DeleteSupersedeOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("lifecycle_transition_invalid",),
                details={"loaded": True},
            )

        if revision_health.state is not HealthState.HEALTHY:
            return DeleteSupersedeOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("lifecycle_transition_invalid",),
                details={"loaded": True},
            )

        if registry_health.state is not HealthState.HEALTHY:
            return DeleteSupersedeOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("lifecycle_transition_invalid",),
                details={"loaded": True},
            )

        return DeleteSupersedeOperationHealth(
            state=HealthState.HEALTHY,
            reason_codes=("delete_voiceprint_ready", "supersede_voiceprint_ready"),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _find_record(self, voiceprint_id: str) -> VoiceprintRecord | None:
        try:
            parsed = VoiceprintId.parse(voiceprint_id)
            for record in self._registry.list_records():
                if record.voiceprint_id == parsed:
                    return record
        except (VoiceprintRegistryValidationError, Exception):
            return None
        return None

    def _failure(
        self,
        *,
        operation_id: str,
        failure_category: DeleteSupersedeFailureCategory,
        reason_code: str,
        voiceprint_id: str | None,
        previous_voiceprint_id: str | None,
        active_voiceprint_id: str | None,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> DeleteSupersedeFailureResult:
        return DeleteSupersedeFailureResult(
            success=False,
            operation_id=operation_id,
            operation_status=VoiceprintOperationStatus.FAILED,
            failure_category=failure_category,
            reason_code=_safe_token(reason_code, failure_category.value) or failure_category.value,
            voiceprint_id=voiceprint_id,
            previous_voiceprint_id=previous_voiceprint_id,
            active_voiceprint_id=active_voiceprint_id,
            operation_timestamp=_utcnow_iso(),
            safe_diagnostics=_sanitize_metadata(diagnostics),
        )


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


def _operation_id() -> str:
    return f"op_{uuid4().hex[:12]}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
