"""Generation orchestrator for Voiceprint pipeline workflows.

This layer owns asynchronous workflow orchestration and status progression for
Voiceprint generation. It coordinates validation, quality, model execution,
persistence, and integrity services without implementing their domain logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile
from typing import Protocol
from uuid import uuid4

from .artifact_integrity import ArtifactIntegrityValidator, IntegritySeverity
from .artifact_persistence import (
    ArtifactPersistenceEngine,
    ArtifactPersistenceError,
    PersistArtifactRequest,
)
from .configuration import VoiceIdentityConfigurationError, VoiceIdentityConfigurationManager
from .health_state import HealthState
from .voiceprint_registry import VoiceprintId

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")
_IDENTIFIER_PATTERN = re_compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class GenerationStatus(StrEnum):
    """Deterministic status progression for generation workflows."""

    QUEUED = "queued"
    VALIDATING = "validating"
    QUALITY_SCORING = "quality_scoring"
    GENERATING = "generating"
    PERSISTING = "persisting"
    VALIDATING_INTEGRITY = "validating_integrity"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationFailureCategory(StrEnum):
    """Safe failure taxonomy for generation orchestration."""

    VALIDATION_FAILED = "validation_failed"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    QUALITY_THRESHOLD_NOT_MET = "quality_threshold_not_met"
    QUALITY_CONFIGURATION_INVALID = "quality_configuration_invalid"
    QUALITY_INPUT_INVALID = "quality_input_invalid"
    QUALITY_INTERNAL_ERROR = "quality_internal_error"
    MODEL_EXECUTION_FAILED = "model_execution_failed"
    PERSISTENCE_FAILED = "persistence_failed"
    INTEGRITY_VALIDATION_FAILED = "integrity_validation_failed"
    CANCELLED = "cancelled"
    CONFIGURATION_INVALID = "configuration_invalid"
    UNSUPPORTED_MODEL = "unsupported_model"
    GENERATION_TIMEOUT = "generation_timeout"


class GenerationOrchestratorError(Exception):
    """Base exception for generation orchestration failures."""


class GenerationOrchestratorNotLoadedError(GenerationOrchestratorError):
    """Raised when orchestration is attempted after unload."""


class _GenerationCancelledError(GenerationOrchestratorError):
    """Internal cancellation sentinel for deterministic status handling."""


@dataclass(slots=True, frozen=True)
class GenerationIdentifiers:
    """Stable identifiers for one generation workflow request."""

    generation_id: str
    subject_id: str
    current_voiceprint_id: str | None
    voice_profile_id: str | None


@dataclass(slots=True, frozen=True)
class GenerationContext:
    """Workflow context references for correlation and enrollment provenance."""

    source: str
    enrollment_reference: str | None
    correlation_id: str | None
    request_id: str | None


@dataclass(slots=True, frozen=True)
class GenerationOptions:
    """Generation workflow execution options."""

    model_preference: str | None
    timeout_seconds: float | None
    activate: bool


@dataclass(slots=True, frozen=True)
class GenerationRequest:
    """Authoritative generation-oriented request contract."""

    identifiers: GenerationIdentifiers
    context: GenerationContext
    options: GenerationOptions
    sample_references: tuple[str, ...]
    enrollment_references: tuple[str, ...]
    prepared_enrollment_inputs: tuple[str, ...]
    requested_at: str

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        sample_references: tuple[str, ...] | list[str],
        source: str,
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
    ) -> GenerationRequest:
        normalized_generation_id = generation_id or f"gen_{uuid4().hex[:12]}"
        _validate_identifier(normalized_generation_id)
        _validate_identifier(subject_id)
        if current_voiceprint_id is not None:
            _validate_identifier(current_voiceprint_id)
        if voice_profile_id is not None:
            _validate_identifier(voice_profile_id)

        sample_refs = tuple(sample_references)
        enrollment_refs = tuple(enrollment_references)
        prepared_inputs = tuple(prepared_enrollment_inputs)

        return cls(
            identifiers=GenerationIdentifiers(
                generation_id=normalized_generation_id,
                subject_id=subject_id,
                current_voiceprint_id=current_voiceprint_id,
                voice_profile_id=voice_profile_id,
            ),
            context=GenerationContext(
                source=_safe_token_or_default(source, "unknown"),
                enrollment_reference=_safe_token_or_none(enrollment_reference),
                correlation_id=_safe_token_or_none(correlation_id),
                request_id=_safe_token_or_none(request_id),
            ),
            options=GenerationOptions(
                model_preference=_safe_token_or_none(model_preference),
                timeout_seconds=timeout_seconds,
                activate=activate,
            ),
            sample_references=sample_refs,
            enrollment_references=enrollment_refs,
            prepared_enrollment_inputs=prepared_inputs,
            requested_at=_utcnow_iso(),
        )


@dataclass(slots=True, frozen=True)
class ValidationSummary:
    """Safe summary projected from sample-validation pipeline output."""

    passed: bool
    reason_code: str
    sample_count: int
    findings: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class QualitySummary:
    """Safe summary projected from quality-scoring pipeline output."""

    passed: bool
    reason_code: str
    score: float | None
    threshold: float | None
    findings: tuple[str, ...]
    status: str = "acceptable"
    recommendation: str = "generation_allowed"
    threshold_outcome: str = "pass"
    score_breakdown: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, bool | int | float | str | None] = field(default_factory=dict)
    failure_category: str = ""


@dataclass(slots=True, frozen=True)
class IntegrityValidationSummary:
    """Safe summary projected from artifact integrity-validation output."""

    passed: bool
    reason_codes: tuple[str, ...]
    finding_count: int


@dataclass(slots=True, frozen=True)
class GenerationStatusEvent:
    """One timestamped status transition event."""

    status: GenerationStatus
    reason_code: str | None
    timestamp: str


@dataclass(slots=True, frozen=True)
class GenerationStatusSnapshot:
    """Read-only status projection for one generation identifier."""

    generation_id: str
    current_status: GenerationStatus
    history: tuple[GenerationStatusEvent, ...]


@dataclass(slots=True, frozen=True)
class GenerationSuccessResult:
    """Safe success contract for completed generation workflows."""

    success: bool
    generation_id: str
    status: GenerationStatus
    voiceprint_id: str
    artifact_id: str
    revision: int
    lineage_root_id: str
    model_name: str
    model_version: str
    schema_version: int
    validation_summary: ValidationSummary
    quality_summary: QualitySummary
    integrity_summary: IntegrityValidationSummary
    status_history: tuple[GenerationStatusEvent, ...]
    requested_at: str
    completed_at: str
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class GenerationFailureResult:
    """Safe failure contract for incomplete generation workflows."""

    success: bool
    generation_id: str
    status: GenerationStatus
    failure_category: GenerationFailureCategory
    reason_code: str
    validation_summary: ValidationSummary | None
    quality_summary: QualitySummary | None
    integrity_summary: IntegrityValidationSummary | None
    status_history: tuple[GenerationStatusEvent, ...]
    requested_at: str
    completed_at: str
    diagnostics: dict[str, bool | int | float | str | None]


GenerationResult = GenerationSuccessResult | GenerationFailureResult


@dataclass(slots=True, frozen=True)
class GenerationOrchestratorHealth:
    """Orchestrator readiness payload for health-engine integration."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class SampleValidationResult:
    """Validation pipeline projection consumed by orchestration."""

    passed: bool
    reason_code: str
    sample_count: int
    findings: tuple[str, ...] = ()
    status: str = "valid"
    highest_severity: str = "info"
    failure_category: str = ""
    recommend_continue: bool = True
    diagnostics: dict[str, bool | int | float | str | None] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class QualityEvaluationResult:
    """Quality-scoring pipeline projection consumed by orchestration."""

    passed: bool
    reason_code: str
    score: float | None
    threshold: float | None
    findings: tuple[str, ...] = ()
    status: str = "acceptable"
    recommendation: str = "generation_allowed"
    threshold_outcome: str = "pass"
    score_breakdown: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, bool | int | float | str | None] = field(default_factory=dict)
    failure_category: str = ""


@dataclass(slots=True, frozen=True)
class ModelArtifactPayload:
    """Model output payload for persistence handoff."""

    voiceprint_id: str
    artifact_id: str
    encrypted_payload: bytes = field(repr=False)
    payload_format_version: int
    encryption_scheme: str
    key_reference: str | None = field(repr=False)
    model_name: str
    model_version: str
    schema_version: int


@dataclass(slots=True, frozen=True)
class ModelExecutionResult:
    """Model execution projection consumed by orchestration."""

    success: bool
    reason_code: str
    artifact: ModelArtifactPayload | None
    diagnostics: dict[str, bool | int | float | str | None]


class SampleValidationPipeline(Protocol):
    """Integration surface for VI-111 sample validation pipeline."""

    async def validate(self, request: GenerationRequest) -> SampleValidationResult:
        """Validate generation input references."""

    async def validate_health(self) -> GenerationOrchestratorHealth:
        """Report validation-pipeline readiness."""


class QualityScoringEngine(Protocol):
    """Integration surface for VI-112 quality-scoring engine."""

    async def score(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
    ) -> QualityEvaluationResult:
        """Score generation quality for validated samples."""

    async def validate_health(self) -> GenerationOrchestratorHealth:
        """Report quality-engine readiness."""


class ModelExecutionProvider(Protocol):
    """Integration surface for VI-113 model execution provider."""

    async def generate(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
        quality: QualityEvaluationResult,
    ) -> ModelExecutionResult:
        """Generate a provider-owned model artifact payload."""

    async def validate_health(self) -> GenerationOrchestratorHealth:
        """Report model-provider readiness."""


class ContractValidationPipeline:
    """Contract-only validation placeholder for early orchestration stages."""

    async def validate(self, request: GenerationRequest) -> SampleValidationResult:
        _ = request
        return SampleValidationResult(
            passed=True,
            reason_code="validation_contract_ready",
            sample_count=0,
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_validation_contract_ready",),
            details={"loaded": True},
        )


class ContractQualityScoringEngine:
    """Contract-only quality placeholder for early orchestration stages."""

    async def score(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
    ) -> QualityEvaluationResult:
        _ = request
        _ = validation
        return QualityEvaluationResult(
            passed=True,
            reason_code="quality_contract_ready",
            score=None,
            threshold=None,
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_quality_contract_ready",),
            details={"loaded": True},
        )


class ContractModelExecutionProvider:
    """Contract-only model provider that preserves workflow boundaries."""

    async def generate(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
        quality: QualityEvaluationResult,
    ) -> ModelExecutionResult:
        _ = request
        _ = validation
        _ = quality
        return ModelExecutionResult(
            success=False,
            reason_code="model_provider_unavailable",
            artifact=None,
            diagnostics={"provider_ready": False},
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_model_contract_ready",),
            details={"loaded": True},
        )


class GenerationOrchestrator:
    """Coordinates end-to-end Voiceprint generation workflow stages."""

    def __init__(
        self,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        validation_pipeline: SampleValidationPipeline,
        quality_engine: QualityScoringEngine,
        model_provider: ModelExecutionProvider,
        persistence_engine: ArtifactPersistenceEngine,
        integrity_validator: ArtifactIntegrityValidator,
    ) -> None:
        self._config_manager = config_manager
        self._validation_pipeline = validation_pipeline
        self._quality_engine = quality_engine
        self._model_provider = model_provider
        self._persistence_engine = persistence_engine
        self._integrity_validator = integrity_validator
        self._history: dict[str, list[GenerationStatusEvent]] = {}
        self._cancelled_ids: set[str] = set()
        self._loaded = True
        self._cleared = False
        self._lock = asyncio.Lock()

    @classmethod
    def create(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        validation_pipeline: SampleValidationPipeline,
        quality_engine: QualityScoringEngine,
        model_provider: ModelExecutionProvider,
        persistence_engine: ArtifactPersistenceEngine,
        integrity_validator: ArtifactIntegrityValidator,
    ) -> GenerationOrchestrator:
        return cls(
            config_manager=config_manager,
            validation_pipeline=validation_pipeline,
            quality_engine=quality_engine,
            model_provider=model_provider,
            persistence_engine=persistence_engine,
            integrity_validator=integrity_validator,
        )

    async def generate_voiceprint(self, request: GenerationRequest) -> GenerationResult:
        """Run one full generation workflow with deterministic status progression."""
        self._ensure_loaded()
        async with self._lock:
            self._history[request.identifiers.generation_id] = [
                GenerationStatusEvent(
                    status=GenerationStatus.QUEUED,
                    reason_code=None,
                    timestamp=_utcnow_iso(),
                )
            ]
            self._cancelled_ids.discard(request.identifiers.generation_id)

        timeout = request.options.timeout_seconds
        try:
            if timeout is not None and timeout > 0:
                return await asyncio.wait_for(self._run_workflow(request), timeout=timeout)
            return await self._run_workflow(request)
        except asyncio.TimeoutError:
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.GENERATION_TIMEOUT,
                reason_code="generation_timeout",
                validation=None,
                quality=None,
                integrity=None,
                final_status=GenerationStatus.FAILED,
            )

    async def cancel_generation(self, generation_id: str) -> bool:
        """Mark an in-flight generation as cancelled."""
        self._ensure_loaded()
        async with self._lock:
            history = self._history.get(generation_id)
            if not history:
                return False
            terminal = history[-1].status in {
                GenerationStatus.COMPLETED,
                GenerationStatus.FAILED,
                GenerationStatus.CANCELLED,
            }
            if terminal:
                return False
            self._cancelled_ids.add(generation_id)
            return True

    async def get_status(self, generation_id: str) -> GenerationStatusSnapshot | None:
        """Return status snapshot for one generation id."""
        history = self._history.get(generation_id)
        if not history:
            return None
        return GenerationStatusSnapshot(
            generation_id=generation_id,
            current_status=history[-1].status,
            history=tuple(history),
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        """Validate orchestrator readiness with dependency projection."""
        if not self._loaded:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_orchestrator_not_loaded",),
                details={"loaded": False},
            )

        try:
            _ = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("configuration_invalid",),
                details={"loaded": True},
            )

        validation_health = await self._validation_pipeline.validate_health()
        if validation_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_validation_failed",),
                details={"loaded": True},
            )

        quality_health = await self._quality_engine.validate_health()
        if quality_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_quality_failed",),
                details={"loaded": True},
            )

        model_health = await self._model_provider.validate_health()
        if model_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_model_failed",),
                details={"loaded": True},
            )

        persistence_health = await self._persistence_engine.validate_health()
        if persistence_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_persistence_failed",),
                details={"loaded": True},
            )

        integrity_health = await self._integrity_validator.validate_health()
        if integrity_health.state is not HealthState.HEALTHY:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("generation_integrity_failed",),
                details={"loaded": True},
            )

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_orchestrator_ready",),
            details={
                "loaded": True,
                "tracked_generations": len(self._history),
            },
        )

    def clear(self) -> None:
        self._loaded = False
        self._history = {}
        self._cancelled_ids = set()
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    async def _run_workflow(self, request: GenerationRequest) -> GenerationResult:
        validation: ValidationSummary | None = None
        quality: QualitySummary | None = None

        try:
            await self._check_cancelled(request.identifiers.generation_id)
            await self._transition(request.identifiers.generation_id, GenerationStatus.VALIDATING)

            selected_model = self._resolve_model_preference(request)

            try:
                validation_result = await self._validation_pipeline.validate(request)
            except Exception:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.VALIDATION_FAILED,
                    reason_code="generation_validation_failed",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )
            validation = ValidationSummary(
                passed=validation_result.passed,
                reason_code=_safe_reason(validation_result.reason_code, "validation_failed"),
                sample_count=validation_result.sample_count,
                findings=_normalize_reason_codes(validation_result.findings),
            )
            if not validation_result.passed:
                category = GenerationFailureCategory.VALIDATION_FAILED
                if validation.reason_code == GenerationFailureCategory.INSUFFICIENT_SAMPLES.value:
                    category = GenerationFailureCategory.INSUFFICIENT_SAMPLES
                return await self._build_failure(
                    request=request,
                    category=category,
                    reason_code=validation.reason_code,
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )

            await self._check_cancelled(request.identifiers.generation_id)
            await self._transition(request.identifiers.generation_id, GenerationStatus.QUALITY_SCORING)

            try:
                quality_result = await self._quality_engine.score(
                    request=request,
                    validation=validation_result,
                )
            except Exception:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.QUALITY_THRESHOLD_NOT_MET,
                    reason_code="generation_quality_failed",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )
            quality = QualitySummary(
                passed=quality_result.passed,
                reason_code=_safe_reason(quality_result.reason_code, "quality_threshold_not_met"),
                score=quality_result.score,
                threshold=quality_result.threshold,
                findings=_normalize_reason_codes(quality_result.findings),
                status=_safe_reason(quality_result.status, "acceptable"),
                recommendation=_safe_reason(quality_result.recommendation, "generation_allowed"),
                threshold_outcome=_safe_reason(quality_result.threshold_outcome, "pass"),
                score_breakdown=dict(quality_result.score_breakdown),
                diagnostics=dict(quality_result.diagnostics),
                failure_category=_safe_reason(quality_result.failure_category, ""),
            )
            if not quality_result.passed:
                return await self._build_failure(
                    request=request,
                    category=_map_quality_failure_category(quality_result),
                    reason_code=quality.reason_code,
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )

            await self._check_cancelled(request.identifiers.generation_id)
            await self._transition(request.identifiers.generation_id, GenerationStatus.GENERATING)

            try:
                model_result = await self._model_provider.generate(
                    request=request,
                    validation=validation_result,
                    quality=quality_result,
                )
            except Exception:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                    reason_code="generation_model_failed",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )
            if not model_result.success or model_result.artifact is None:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                    reason_code=_safe_reason(model_result.reason_code, "generation_model_failed"),
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )

            artifact = model_result.artifact
            if artifact.model_name != selected_model:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.UNSUPPORTED_MODEL,
                    reason_code="unsupported_model",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )

            await self._check_cancelled(request.identifiers.generation_id)
            await self._transition(request.identifiers.generation_id, GenerationStatus.PERSISTING)

            persist_request = PersistArtifactRequest(
                voiceprint_id=artifact.voiceprint_id,
                artifact_id=artifact.artifact_id,
                subject_id=request.identifiers.subject_id,
                current_voiceprint_id=request.identifiers.current_voiceprint_id,
                encrypted=True,
                encrypted_payload=artifact.encrypted_payload,
                payload_format_version=artifact.payload_format_version,
                encryption_scheme=artifact.encryption_scheme,
                key_reference=artifact.key_reference,
                model_name=artifact.model_name,
                model_version=artifact.model_version,
                schema_version=artifact.schema_version,
                activate=request.options.activate,
            )

            try:
                persist_result = await self._persistence_engine.persist_artifact(persist_request)
            except ArtifactPersistenceError:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.PERSISTENCE_FAILED,
                    reason_code="generation_persistence_failed",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )

            await self._check_cancelled(request.identifiers.generation_id)
            await self._transition(
                request.identifiers.generation_id,
                GenerationStatus.VALIDATING_INTEGRITY,
            )

            try:
                integrity_result = await self._integrity_validator.validate_voiceprint(
                    VoiceprintId.parse(persist_result.voiceprint_id)
                )
            except Exception:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.INTEGRITY_VALIDATION_FAILED,
                    reason_code="generation_integrity_failed",
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )
            integrity_summary = IntegrityValidationSummary(
                passed=integrity_result.status is IntegritySeverity.HEALTHY,
                reason_codes=tuple(
                    sorted({
                        _safe_reason(finding.reason_code, "integrity_validation_failed")
                        for finding in integrity_result.findings
                    })
                ),
                finding_count=len(integrity_result.findings),
            )

            if not integrity_summary.passed:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.INTEGRITY_VALIDATION_FAILED,
                    reason_code="integrity_validation_failed",
                    validation=validation,
                    quality=quality,
                    integrity=integrity_summary,
                    final_status=GenerationStatus.FAILED,
                )

            await self._transition(request.identifiers.generation_id, GenerationStatus.COMPLETED)
            history = tuple(self._history[request.identifiers.generation_id])
            return GenerationSuccessResult(
                success=True,
                generation_id=request.identifiers.generation_id,
                status=GenerationStatus.COMPLETED,
                voiceprint_id=persist_result.voiceprint_id,
                artifact_id=persist_result.artifact_id,
                revision=persist_result.revision,
                lineage_root_id=persist_result.lineage_root_id,
                model_name=artifact.model_name,
                model_version=artifact.model_version,
                schema_version=artifact.schema_version,
                validation_summary=validation,
                quality_summary=quality,
                integrity_summary=integrity_summary,
                status_history=history,
                requested_at=request.requested_at,
                completed_at=_utcnow_iso(),
                diagnostics={
                    "status_count": len(history),
                    "sample_count": len(request.sample_references),
                    "enrollment_ref_count": len(request.enrollment_references),
                },
            )
        except _GenerationCancelledError:
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.CANCELLED,
                reason_code="cancelled",
                validation=validation,
                quality=quality,
                integrity=None,
                final_status=GenerationStatus.CANCELLED,
            )
        except VoiceIdentityConfigurationError:
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.CONFIGURATION_INVALID,
                reason_code="configuration_invalid",
                validation=validation,
                quality=quality,
                integrity=None,
                final_status=GenerationStatus.FAILED,
            )
        except GenerationOrchestratorError as err:
            reason_code = str(err)
            if reason_code == GenerationFailureCategory.UNSUPPORTED_MODEL.value:
                return await self._build_failure(
                    request=request,
                    category=GenerationFailureCategory.UNSUPPORTED_MODEL,
                    reason_code=reason_code,
                    validation=validation,
                    quality=quality,
                    integrity=None,
                    final_status=GenerationStatus.FAILED,
                )
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.CONFIGURATION_INVALID,
                reason_code="configuration_invalid",
                validation=validation,
                quality=quality,
                integrity=None,
                final_status=GenerationStatus.FAILED,
            )
        except ArtifactPersistenceError:
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.PERSISTENCE_FAILED,
                reason_code="generation_persistence_failed",
                validation=validation,
                quality=quality,
                integrity=None,
                final_status=GenerationStatus.FAILED,
            )
        except Exception:
            return await self._build_failure(
                request=request,
                category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                reason_code="generation_model_failed",
                validation=validation,
                quality=quality,
                integrity=None,
                final_status=GenerationStatus.FAILED,
            )

    async def _build_failure(
        self,
        *,
        request: GenerationRequest,
        category: GenerationFailureCategory,
        reason_code: str,
        validation: ValidationSummary | None,
        quality: QualitySummary | None,
        integrity: IntegrityValidationSummary | None,
        final_status: GenerationStatus,
    ) -> GenerationFailureResult:
        await self._transition(
            request.identifiers.generation_id,
            final_status,
            reason_code=_safe_reason(reason_code, category.value),
        )
        history = tuple(self._history[request.identifiers.generation_id])
        return GenerationFailureResult(
            success=False,
            generation_id=request.identifiers.generation_id,
            status=final_status,
            failure_category=category,
            reason_code=_safe_reason(reason_code, category.value),
            validation_summary=validation,
            quality_summary=quality,
            integrity_summary=integrity,
            status_history=history,
            requested_at=request.requested_at,
            completed_at=_utcnow_iso(),
            diagnostics={
                "status_count": len(history),
                "sample_count": len(request.sample_references),
                "source": request.context.source,
            },
        )

    async def _check_cancelled(self, generation_id: str) -> None:
        if generation_id in self._cancelled_ids:
            raise _GenerationCancelledError("cancelled")

    async def _transition(
        self,
        generation_id: str,
        target: GenerationStatus,
        reason_code: str | None = None,
    ) -> None:
        async with self._lock:
            history = self._history[generation_id]
            current = history[-1].status
            if target is current:
                return
            if target not in _ALLOWED_TRANSITIONS[current]:
                raise GenerationOrchestratorError("generation_status_transition_invalid")
            history.append(
                GenerationStatusEvent(
                    status=target,
                    reason_code=_safe_reason(reason_code, None) if reason_code else None,
                    timestamp=_utcnow_iso(),
                )
            )

    def _resolve_model_preference(self, request: GenerationRequest) -> str:
        config = self._config_manager.config
        selected = request.options.model_preference or config.generation.model_preference
        normalized = _safe_token_or_default(selected, config.generation.model_preference)
        if normalized not in config.generation.supported_models:
            raise GenerationOrchestratorError("unsupported_model")
        return normalized

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise GenerationOrchestratorNotLoadedError("generation_orchestrator_not_loaded")


_ALLOWED_TRANSITIONS: dict[GenerationStatus, set[GenerationStatus]] = {
    GenerationStatus.QUEUED: {
        GenerationStatus.VALIDATING,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.VALIDATING: {
        GenerationStatus.QUALITY_SCORING,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.QUALITY_SCORING: {
        GenerationStatus.GENERATING,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.GENERATING: {
        GenerationStatus.PERSISTING,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.PERSISTING: {
        GenerationStatus.VALIDATING_INTEGRITY,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.VALIDATING_INTEGRITY: {
        GenerationStatus.COMPLETED,
        GenerationStatus.CANCELLED,
        GenerationStatus.FAILED,
    },
    GenerationStatus.COMPLETED: set(),
    GenerationStatus.FAILED: set(),
    GenerationStatus.CANCELLED: set(),
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_identifier(value: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value.strip()):
        raise GenerationOrchestratorError("generation_identifier_invalid")


def _safe_reason(reason_code: str | None, fallback: str | None) -> str:
    if reason_code and _SAFE_TOKEN_PATTERN.fullmatch(reason_code):
        return reason_code
    if fallback and _SAFE_TOKEN_PATTERN.fullmatch(fallback):
        return fallback
    return "generation_failed"


def _safe_token_or_default(value: str | None, fallback: str) -> str:
    if value is None:
        return _safe_reason(fallback, "unknown")
    normalized = value.strip().lower()
    if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
        return normalized
    return _safe_reason(fallback, "unknown")


def _safe_token_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
        return normalized
    return None


def _normalize_reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        safe_value = _safe_reason(value, "generation_failed")
        if safe_value not in normalized:
            normalized.append(safe_value)
    return tuple(normalized)


def _map_quality_failure_category(quality_result: QualityEvaluationResult) -> GenerationFailureCategory:
    quality_failure = _safe_reason(
        quality_result.failure_category,
        quality_result.reason_code,
    )
    if quality_failure == GenerationFailureCategory.QUALITY_CONFIGURATION_INVALID.value:
        return GenerationFailureCategory.QUALITY_CONFIGURATION_INVALID
    if quality_failure == GenerationFailureCategory.QUALITY_INPUT_INVALID.value:
        return GenerationFailureCategory.QUALITY_INPUT_INVALID
    if quality_failure == GenerationFailureCategory.QUALITY_INTERNAL_ERROR.value:
        return GenerationFailureCategory.QUALITY_INTERNAL_ERROR
    return GenerationFailureCategory.QUALITY_THRESHOLD_NOT_MET