"""Sample validation pipeline for generation input readiness.

This module validates generation request structure and metadata readiness for
progression into downstream quality/model stages. It does not perform quality
scoring, model execution, persistence, or integrity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import compile as re_compile

from .configuration import VoiceIdentityConfigurationError, VoiceIdentityConfigurationManager
from .generation_orchestrator import (
    GenerationOrchestratorHealth,
    GenerationRequest,
    SampleValidationPipeline,
    SampleValidationResult,
)
from .health_state import HealthState

_REFERENCE_PATTERN = re_compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$")


class ValidationStatus(StrEnum):
    """Validation outcome status."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


class ValidationSeverity(StrEnum):
    """Validation severity levels for findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationFailureCategory(StrEnum):
    """Failure taxonomy for validation readiness."""

    REQUEST_INVALID = "request_invalid"
    SAMPLE_REFERENCE_MISSING = "sample_reference_missing"
    SAMPLE_REFERENCE_INVALID = "sample_reference_invalid"
    ENROLLMENT_REFERENCE_MISSING = "enrollment_reference_missing"
    ENROLLMENT_REFERENCE_INVALID = "enrollment_reference_invalid"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    DUPLICATE_SAMPLES = "duplicate_samples"
    UNSUPPORTED_CONFIGURATION = "unsupported_configuration"
    VALIDATION_CONFIGURATION_INVALID = "validation_configuration_invalid"
    VALIDATION_INTERNAL_ERROR = "validation_internal_error"


@dataclass(slots=True, frozen=True)
class ValidationFinding:
    """Machine-readable validation finding."""

    severity: ValidationSeverity
    category: ValidationFailureCategory
    reason_code: str
    blocking: bool
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class ValidationResult:
    """Structured validation result for generation input readiness."""

    status: ValidationStatus
    findings: tuple[ValidationFinding, ...]
    diagnostics: dict[str, bool | int | float | str | None]
    recommend_continue: bool


class SampleValidationPipelineProvider(SampleValidationPipeline):
    """Real validation provider for generation request and sample metadata."""

    def __init__(self, *, config_manager: VoiceIdentityConfigurationManager) -> None:
        self._config_manager = config_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
    ) -> SampleValidationPipelineProvider:
        return cls(config_manager=config_manager)

    async def validate(self, request: GenerationRequest) -> SampleValidationResult:
        if not self._loaded:
            return SampleValidationResult(
                passed=False,
                reason_code="sample_validation_not_loaded",
                sample_count=0,
                findings=("validation_internal_error",),
                status=ValidationStatus.INVALID.value,
                highest_severity=ValidationSeverity.ERROR.value,
                failure_category=ValidationFailureCategory.VALIDATION_INTERNAL_ERROR.value,
                recommend_continue=False,
                diagnostics={"loaded": False},
            )

        try:
            config = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return SampleValidationResult(
                passed=False,
                reason_code=ValidationFailureCategory.VALIDATION_CONFIGURATION_INVALID.value,
                sample_count=len(request.sample_references),
                findings=(ValidationFailureCategory.VALIDATION_CONFIGURATION_INVALID.value,),
                status=ValidationStatus.INVALID.value,
                highest_severity=ValidationSeverity.ERROR.value,
                failure_category=ValidationFailureCategory.VALIDATION_CONFIGURATION_INVALID.value,
                recommend_continue=False,
                diagnostics={"loaded": True},
            )

        try:
            findings: list[ValidationFinding] = []

            if not request.identifiers.generation_id or not request.identifiers.subject_id:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.REQUEST_INVALID,
                        blocking=True,
                    )
                )

            if not request.context.source:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.REQUEST_INVALID,
                        blocking=True,
                    )
                )

            sample_refs = request.sample_references
            if not sample_refs:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.SAMPLE_REFERENCE_MISSING,
                        blocking=True,
                    )
                )

            if len(sample_refs) < config.generation.min_sample_count:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.INSUFFICIENT_SAMPLES,
                        blocking=True,
                        details={
                            "sample_count": len(sample_refs),
                            "minimum_required": config.generation.min_sample_count,
                        },
                    )
                )

            if len(sample_refs) > config.generation.max_sample_count:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.UNSUPPORTED_CONFIGURATION,
                        blocking=True,
                        details={
                            "sample_count": len(sample_refs),
                            "maximum_allowed": config.generation.max_sample_count,
                        },
                    )
                )

            duplicates = _duplicate_count(sample_refs)
            if duplicates > 0:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.DUPLICATE_SAMPLES,
                        blocking=True,
                        details={"duplicate_count": duplicates},
                    )
                )

            if any(not _is_valid_reference(ref) for ref in sample_refs):
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.SAMPLE_REFERENCE_INVALID,
                        blocking=True,
                    )
                )

            if not request.enrollment_references:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.WARNING,
                        category=ValidationFailureCategory.ENROLLMENT_REFERENCE_MISSING,
                        blocking=False,
                    )
                )

            if any(not _is_valid_reference(ref) for ref in request.enrollment_references):
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.ENROLLMENT_REFERENCE_INVALID,
                        blocking=True,
                    )
                )

            selected_model = request.options.model_preference or config.generation.model_preference
            if selected_model not in config.generation.supported_models:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.UNSUPPORTED_CONFIGURATION,
                        blocking=True,
                    )
                )

            if request.options.timeout_seconds is not None and request.options.timeout_seconds <= 0:
                findings.append(
                    _finding(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationFailureCategory.REQUEST_INVALID,
                        blocking=True,
                    )
                )

            result = _result_from_findings(findings=findings, sample_count=len(sample_refs))
            return SampleValidationResult(
                passed=result.status is ValidationStatus.VALID
                or result.status is ValidationStatus.WARNING,
                reason_code=_primary_reason_code(result.findings),
                sample_count=len(sample_refs),
                findings=tuple(finding.reason_code for finding in result.findings),
                status=result.status.value,
                highest_severity=_highest_severity(result.findings).value,
                failure_category=_primary_reason_code(result.findings),
                recommend_continue=result.recommend_continue,
                diagnostics=result.diagnostics,
            )
        except Exception:
            return SampleValidationResult(
                passed=False,
                reason_code=ValidationFailureCategory.VALIDATION_INTERNAL_ERROR.value,
                sample_count=0,
                findings=(ValidationFailureCategory.VALIDATION_INTERNAL_ERROR.value,),
                status=ValidationStatus.INVALID.value,
                highest_severity=ValidationSeverity.ERROR.value,
                failure_category=ValidationFailureCategory.VALIDATION_INTERNAL_ERROR.value,
                recommend_continue=False,
                diagnostics={"loaded": True},
            )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        if not self._loaded:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("sample_validation_not_loaded",),
                details={"loaded": False},
            )

        try:
            _ = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("sample_validation_configuration_invalid",),
                details={"loaded": True},
            )

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("sample_validation_ready",),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


def _is_valid_reference(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    return _REFERENCE_PATTERN.fullmatch(normalized) is not None


def _duplicate_count(values: tuple[str, ...]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for value in values:
        if value in seen:
            duplicates += 1
            continue
        seen.add(value)
    return duplicates


def _finding(
    *,
    severity: ValidationSeverity,
    category: ValidationFailureCategory,
    blocking: bool,
    details: dict[str, bool | int | float | str | None] | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        severity=severity,
        category=category,
        reason_code=category.value,
        blocking=blocking,
        details=details or {},
    )


def _highest_severity(findings: tuple[ValidationFinding, ...]) -> ValidationSeverity:
    if any(finding.severity is ValidationSeverity.ERROR for finding in findings):
        return ValidationSeverity.ERROR
    if any(finding.severity is ValidationSeverity.WARNING for finding in findings):
        return ValidationSeverity.WARNING
    return ValidationSeverity.INFO


def _result_from_findings(*, findings: list[ValidationFinding], sample_count: int) -> ValidationResult:
    if not findings:
        return ValidationResult(
            status=ValidationStatus.VALID,
            findings=(),
            diagnostics={
                "sample_count": sample_count,
                "finding_count": 0,
                "blocking_count": 0,
            },
            recommend_continue=True,
        )

    frozen_findings = tuple(findings)
    blocking_count = sum(1 for finding in frozen_findings if finding.blocking)
    if blocking_count > 0:
        status = ValidationStatus.INVALID
        recommend_continue = False
    else:
        status = ValidationStatus.WARNING
        recommend_continue = True

    return ValidationResult(
        status=status,
        findings=frozen_findings,
        diagnostics={
            "sample_count": sample_count,
            "finding_count": len(frozen_findings),
            "blocking_count": blocking_count,
        },
        recommend_continue=recommend_continue,
    )


def _primary_reason_code(findings: tuple[ValidationFinding, ...]) -> str:
    for finding in findings:
        if finding.blocking:
            return finding.reason_code
    if findings:
        return findings[0].reason_code
    return "sample_validation_ready"