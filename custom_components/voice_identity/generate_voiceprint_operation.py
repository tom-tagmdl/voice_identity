"""GenerateVoiceprint operation boundary for consumers.

This module provides the public operation layer for voiceprint generation by
composing the existing generation orchestrator and preserving subsystem
taxonomy and summaries without reimplementing workflow stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile

from .generation_orchestrator import (
    GenerationFailureCategory,
    GenerationFailureResult,
    GenerationOrchestrator,
    GenerationOrchestratorError,
    GenerationOrchestratorHealth,
    GenerationRequest,
    GenerationStatus,
    GenerationStatusEvent,
    GenerationSuccessResult,
    IntegrityValidationSummary,
    QualitySummary,
    ValidationSummary,
)
from .health_state import HealthState

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class GenerateVoiceprintOperationStatus(StrEnum):
    """Consumer-facing operation status."""

    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerateVoiceprintFailureCategory(StrEnum):
    """Operation-level failure taxonomy."""

    OPERATION_INVALID = "operation_invalid"
    OPERATION_CANCELLED = "operation_cancelled"
    OPERATION_FAILED = "operation_failed"
    VALIDATION_FAILED = "validation_failed"
    QUALITY_FAILED = "quality_failed"
    MODEL_FAILED = "model_failed"
    PERSISTENCE_FAILED = "persistence_failed"
    INTEGRITY_FAILED = "integrity_failed"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


@dataclass(slots=True, frozen=True)
class GenerateVoiceprintOperationEvent:
    """Timestamped operation status transition event."""

    status: GenerateVoiceprintOperationStatus
    reason_code: str | None
    timestamp: str


@dataclass(slots=True, frozen=True)
class GenerateVoiceprintOperationSnapshot:
    """Read-only operation status snapshot."""

    operation_id: str
    generation_id: str | None
    current_status: GenerateVoiceprintOperationStatus
    history: tuple[GenerateVoiceprintOperationEvent, ...]


@dataclass(slots=True, frozen=True)
class GenerateVoiceprintRequest:
    """Public operation request contract for voiceprint generation."""

    operation_id: str
    subject_id: str
    source: str
    sample_references: tuple[str, ...]
    enrollment_references: tuple[str, ...] = ()
    prepared_enrollment_inputs: tuple[str, ...] = ()
    model_preference: str | None = None
    timeout_seconds: float | None = None
    activate: bool = True
    generation_id: str | None = None
    current_voiceprint_id: str | None = None
    voice_profile_id: str | None = None
    enrollment_reference: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        subject_id: str,
        source: str,
        sample_references: tuple[str, ...] | list[str],
        enrollment_references: tuple[str, ...] | list[str] = (),
        prepared_enrollment_inputs: tuple[str, ...] | list[str] = (),
        model_preference: str | None = None,
        timeout_seconds: float | None = None,
        activate: bool = True,
        generation_id: str | None = None,
        current_voiceprint_id: str | None = None,
        voice_profile_id: str | None = None,
        enrollment_reference: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> GenerateVoiceprintRequest:
        return cls(
            operation_id=_safe_token(operation_id, "operation"),
            subject_id=subject_id,
            source=source,
            sample_references=tuple(sample_references),
            enrollment_references=tuple(enrollment_references),
            prepared_enrollment_inputs=tuple(prepared_enrollment_inputs),
            model_preference=model_preference,
            timeout_seconds=timeout_seconds,
            activate=activate,
            generation_id=generation_id,
            current_voiceprint_id=current_voiceprint_id,
            voice_profile_id=voice_profile_id,
            enrollment_reference=enrollment_reference,
            correlation_id=correlation_id,
            request_id=request_id,
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class OperationPersistenceSummary:
    """Operation-level persistence projection from orchestrator success output."""

    persisted: bool
    artifact_id: str
    revision: int
    lineage_root_id: str


@dataclass(slots=True, frozen=True)
class GenerateVoiceprintSuccessResult:
    """Public success contract for GenerateVoiceprint operation."""

    success: bool
    operation_id: str
    generation_id: str
    status: GenerateVoiceprintOperationStatus
    voiceprint_id: str
    artifact_id: str
    revision: int
    lineage_root_id: str
    validation_summary: ValidationSummary
    quality_summary: QualitySummary
    persistence_summary: OperationPersistenceSummary
    integrity_summary: IntegrityValidationSummary
    operation_status_history: tuple[GenerateVoiceprintOperationEvent, ...]
    workflow_status_history: tuple[GenerationStatusEvent, ...]
    requested_at: str
    completed_at: str
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class GenerateVoiceprintFailureResult:
    """Public failure contract for GenerateVoiceprint operation."""

    success: bool
    operation_id: str
    generation_id: str | None
    status: GenerateVoiceprintOperationStatus
    failure_category: GenerateVoiceprintFailureCategory
    subsystem_failure_category: str
    reason_code: str
    validation_summary: ValidationSummary | None
    quality_summary: QualitySummary | None
    integrity_summary: IntegrityValidationSummary | None
    operation_status_history: tuple[GenerateVoiceprintOperationEvent, ...]
    workflow_status_history: tuple[GenerationStatusEvent, ...]
    requested_at: str
    completed_at: str
    diagnostics: dict[str, bool | int | float | str | None]


GenerateVoiceprintResult = GenerateVoiceprintSuccessResult | GenerateVoiceprintFailureResult


class GenerateVoiceprintOperation:
    """Public operation entry point for complete voiceprint generation."""

    def __init__(self, *, orchestrator: GenerationOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._loaded = True
        self._cleared = False
        self._status: dict[str, list[GenerateVoiceprintOperationEvent]] = {}
        self._generation_ids: dict[str, str] = {}

    @classmethod
    def create(cls, *, orchestrator: GenerationOrchestrator) -> GenerateVoiceprintOperation:
        return cls(orchestrator=orchestrator)

    async def execute(self, request: GenerateVoiceprintRequest) -> GenerateVoiceprintResult:
        if not self._loaded:
            return self._build_operation_failure(
                request=request,
                generation_id=None,
                failure_category=GenerateVoiceprintFailureCategory.OPERATION_FAILED,
                subsystem_failure_category="",
                reason_code="generate_voiceprint_not_loaded",
                validation=None,
                quality=None,
                integrity=None,
                workflow_status_history=(),
                terminal_status=GenerateVoiceprintOperationStatus.FAILED,
                diagnostics={"loaded": False},
            )

        self._status[request.operation_id] = (
            [
                _operation_event(status=GenerateVoiceprintOperationStatus.REQUESTED, reason_code=None),
                _operation_event(status=GenerateVoiceprintOperationStatus.RUNNING, reason_code=None),
            ]
        )

        try:
            generation_request = GenerationRequest.create(
                subject_id=request.subject_id,
                sample_references=request.sample_references,
                source=request.source,
                enrollment_references=request.enrollment_references,
                prepared_enrollment_inputs=request.prepared_enrollment_inputs,
                model_preference=request.model_preference,
                timeout_seconds=request.timeout_seconds,
                activate=request.activate,
                generation_id=request.generation_id,
                current_voiceprint_id=request.current_voiceprint_id,
                voice_profile_id=request.voice_profile_id,
                enrollment_reference=request.enrollment_reference,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
            )
        except GenerationOrchestratorError:
            return self._build_operation_failure(
                request=request,
                generation_id=None,
                failure_category=GenerateVoiceprintFailureCategory.OPERATION_INVALID,
                subsystem_failure_category="",
                reason_code="operation_invalid",
                validation=None,
                quality=None,
                integrity=None,
                workflow_status_history=(),
                terminal_status=GenerateVoiceprintOperationStatus.FAILED,
                diagnostics={"loaded": True},
            )

        self._generation_ids[request.operation_id] = generation_request.identifiers.generation_id
        try:
            result = await self._orchestrator.generate_voiceprint(generation_request)
        except Exception:
            return self._build_operation_failure(
                request=request,
                generation_id=self._generation_ids.get(request.operation_id),
                failure_category=GenerateVoiceprintFailureCategory.OPERATION_INTERNAL_ERROR,
                subsystem_failure_category="",
                reason_code="operation_internal_error",
                validation=None,
                quality=None,
                integrity=None,
                workflow_status_history=(),
                terminal_status=GenerateVoiceprintOperationStatus.FAILED,
                diagnostics={
                    "loaded": True,
                    "error": "operation_internal_error",
                },
            )

        if isinstance(result, GenerationSuccessResult):
            self._status[request.operation_id].append(
                _operation_event(status=GenerateVoiceprintOperationStatus.COMPLETED, reason_code="generate_voiceprint_ready")
            )
            operation_history = tuple(self._status[request.operation_id])
            return GenerateVoiceprintSuccessResult(
                success=True,
                operation_id=request.operation_id,
                generation_id=result.generation_id,
                status=GenerateVoiceprintOperationStatus.COMPLETED,
                voiceprint_id=result.voiceprint_id,
                artifact_id=result.artifact_id,
                revision=result.revision,
                lineage_root_id=result.lineage_root_id,
                validation_summary=result.validation_summary,
                quality_summary=result.quality_summary,
                persistence_summary=OperationPersistenceSummary(
                    persisted=True,
                    artifact_id=result.artifact_id,
                    revision=result.revision,
                    lineage_root_id=result.lineage_root_id,
                ),
                integrity_summary=result.integrity_summary,
                operation_status_history=operation_history,
                workflow_status_history=result.status_history,
                requested_at=request.requested_at,
                completed_at=result.completed_at,
                diagnostics={
                    "loaded": True,
                    "operation_status_count": len(operation_history),
                    "workflow_status_count": len(result.status_history),
                    "sample_count": result.validation_summary.sample_count,
                    "quality_passed": result.quality_summary.passed,
                    "integrity_passed": result.integrity_summary.passed,
                },
            )

        mapped_category, terminal_status = _map_failure(result)
        return self._build_operation_failure(
            request=request,
            generation_id=result.generation_id,
            failure_category=mapped_category,
            subsystem_failure_category=result.failure_category.value,
            reason_code=result.reason_code,
            validation=result.validation_summary,
            quality=result.quality_summary,
            integrity=result.integrity_summary,
            workflow_status_history=result.status_history,
            terminal_status=terminal_status,
            diagnostics={
                "loaded": True,
                "operation_status_count": len(self._status[request.operation_id]) + 1,
                "workflow_status_count": len(result.status_history),
                "sample_count": result.validation_summary.sample_count if result.validation_summary else 0,
            },
        )

    async def get_status(self, operation_id: str) -> GenerateVoiceprintOperationSnapshot | None:
        history = self._status.get(operation_id)
        if not history:
            return None
        generation_id = self._generation_ids.get(operation_id)
        return GenerateVoiceprintOperationSnapshot(
            operation_id=operation_id,
            generation_id=generation_id,
            current_status=history[-1].status,
            history=tuple(history),
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        if not self._loaded:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generate_voiceprint_not_loaded",),
                details={"loaded": False},
            )

        orchestrator_health = await self._orchestrator.validate_health()
        if orchestrator_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_failed",),
                details={"loaded": True},
            )

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generate_voiceprint_ready",),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True
        self._status = {}
        self._generation_ids = {}

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _build_operation_failure(
        self,
        *,
        request: GenerateVoiceprintRequest,
        generation_id: str | None,
        failure_category: GenerateVoiceprintFailureCategory,
        subsystem_failure_category: str,
        reason_code: str,
        validation: ValidationSummary | None,
        quality: QualitySummary | None,
        integrity: IntegrityValidationSummary | None,
        workflow_status_history: tuple[GenerationStatusEvent, ...],
        terminal_status: GenerateVoiceprintOperationStatus,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> GenerateVoiceprintFailureResult:
        operation_events = self._status.setdefault(
            request.operation_id,
            [_operation_event(status=GenerateVoiceprintOperationStatus.REQUESTED, reason_code=None)],
        )
        operation_events.append(
            _operation_event(
                status=terminal_status,
                reason_code=_safe_token(reason_code, failure_category.value),
            )
        )
        operation_history = tuple(operation_events)
        return GenerateVoiceprintFailureResult(
            success=False,
            operation_id=request.operation_id,
            generation_id=generation_id,
            status=terminal_status,
            failure_category=failure_category,
            subsystem_failure_category=_safe_token(subsystem_failure_category, ""),
            reason_code=_safe_token(reason_code, failure_category.value),
            validation_summary=validation,
            quality_summary=quality,
            integrity_summary=integrity,
            operation_status_history=operation_history,
            workflow_status_history=workflow_status_history,
            requested_at=request.requested_at,
            completed_at=_utcnow_iso(),
            diagnostics=_sanitize_metadata(diagnostics),
        )


def _map_failure(
    result: GenerationFailureResult,
) -> tuple[GenerateVoiceprintFailureCategory, GenerateVoiceprintOperationStatus]:
    if result.failure_category is GenerationFailureCategory.CANCELLED:
        return GenerateVoiceprintFailureCategory.OPERATION_CANCELLED, GenerateVoiceprintOperationStatus.CANCELLED

    if result.failure_category in {
        GenerationFailureCategory.VALIDATION_FAILED,
        GenerationFailureCategory.INSUFFICIENT_SAMPLES,
    }:
        return GenerateVoiceprintFailureCategory.VALIDATION_FAILED, GenerateVoiceprintOperationStatus.FAILED

    if result.failure_category in {
        GenerationFailureCategory.QUALITY_THRESHOLD_NOT_MET,
        GenerationFailureCategory.QUALITY_CONFIGURATION_INVALID,
        GenerationFailureCategory.QUALITY_INPUT_INVALID,
        GenerationFailureCategory.QUALITY_INTERNAL_ERROR,
    }:
        return GenerateVoiceprintFailureCategory.QUALITY_FAILED, GenerateVoiceprintOperationStatus.FAILED

    if result.failure_category in {
        GenerationFailureCategory.MODEL_EXECUTION_FAILED,
        GenerationFailureCategory.UNSUPPORTED_MODEL,
    }:
        return GenerateVoiceprintFailureCategory.MODEL_FAILED, GenerateVoiceprintOperationStatus.FAILED

    if result.failure_category is GenerationFailureCategory.PERSISTENCE_FAILED:
        return GenerateVoiceprintFailureCategory.PERSISTENCE_FAILED, GenerateVoiceprintOperationStatus.FAILED

    if result.failure_category is GenerationFailureCategory.INTEGRITY_VALIDATION_FAILED:
        return GenerateVoiceprintFailureCategory.INTEGRITY_FAILED, GenerateVoiceprintOperationStatus.FAILED

    return GenerateVoiceprintFailureCategory.OPERATION_FAILED, GenerateVoiceprintOperationStatus.FAILED


def _operation_event(
    *,
    status: GenerateVoiceprintOperationStatus,
    reason_code: str | None,
) -> GenerateVoiceprintOperationEvent:
    return GenerateVoiceprintOperationEvent(
        status=status,
        reason_code=_safe_token(reason_code, None) if reason_code else None,
        timestamp=_utcnow_iso(),
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


def _safe_token(value: str | None, fallback: str | None) -> str:
    if value is not None:
        normalized = value.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
            return normalized
    if fallback is not None:
        normalized_fallback = fallback.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized_fallback):
            return normalized_fallback
    return ""


def _safe_metadata_value(value: str) -> str:
    normalized = _safe_token(value, "")
    if not normalized:
        return ""
    if "http" in normalized or "/" in normalized or "\\" in normalized:
        return ""
    if "token" in normalized or "secret" in normalized or "key" in normalized:
        return ""
    return normalized


def _is_sensitive_key(key: str) -> bool:
    return any(token in key for token in ("token", "secret", "key", "path", "url"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()