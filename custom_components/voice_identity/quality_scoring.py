"""Quality scoring engine for generation readiness evaluation.

This module evaluates quality of generation inputs after validation and before
model execution. It is deterministic and explainable, and it does not perform
validation policy, model execution, persistence, or integrity logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .configuration import VoiceIdentityConfigurationError, VoiceIdentityConfigurationManager
from .generation_orchestrator import (
    GenerationOrchestratorHealth,
    GenerationRequest,
    QualityEvaluationResult,
    QualityScoringEngine,
    SampleValidationResult,
)
from .health_state import HealthState


class QualityStatus(StrEnum):
    """Quality readiness status."""

    EXCELLENT = "excellent"
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    POOR = "poor"
    FAILED = "failed"


class QualityRecommendation(StrEnum):
    """Quality recommendation for generation gate decisions."""

    GENERATION_RECOMMENDED = "generation_recommended"
    GENERATION_ALLOWED = "generation_allowed"
    GENERATION_WARNING = "generation_warning"
    GENERATION_REJECTED = "generation_rejected"


class QualityThresholdOutcome(StrEnum):
    """Threshold outcome for generation gating."""

    PASS = "pass"
    PASS_WITH_WARNING = "pass_with_warning"
    FAIL = "fail"


class QualityFindingSeverity(StrEnum):
    """Severity levels for quality findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityFailureCategory(StrEnum):
    """Quality failure taxonomy."""

    QUALITY_THRESHOLD_NOT_MET = "quality_threshold_not_met"
    QUALITY_CONFIGURATION_INVALID = "quality_configuration_invalid"
    QUALITY_INPUT_INVALID = "quality_input_invalid"
    QUALITY_INTERNAL_ERROR = "quality_internal_error"


@dataclass(slots=True, frozen=True)
class QualityFinding:
    """Machine-readable quality finding contract."""

    severity: QualityFindingSeverity
    reason_code: str
    score_impact: float
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class QualityScoreBreakdown:
    """Deterministic score factor breakdown."""

    sample_count_score: float
    sample_diversity_score: float
    source_diversity_score: float
    enrollment_completeness_score: float
    metadata_completeness_score: float
    prepared_input_score: float


@dataclass(slots=True, frozen=True)
class QualityScoreResult:
    """Detailed quality scoring result contract."""

    overall_score: float
    breakdown: QualityScoreBreakdown
    status: QualityStatus
    findings: tuple[QualityFinding, ...]
    recommendation: QualityRecommendation
    threshold_outcome: QualityThresholdOutcome
    diagnostics: dict[str, bool | int | float | str | None]
    failure_category: str
    reason_code: str
    passed: bool


class QualityScoringEngineProvider(QualityScoringEngine):
    """Deterministic quality scoring provider for VI-112."""

    def __init__(self, *, config_manager: VoiceIdentityConfigurationManager) -> None:
        self._config_manager = config_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
    ) -> QualityScoringEngineProvider:
        return cls(config_manager=config_manager)

    async def score(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
    ) -> QualityEvaluationResult:
        if not self._loaded:
            return _as_evaluation_result(
                _internal_error_result(
                    reason_code="quality_scoring_not_loaded",
                    diagnostics={"loaded": False},
                )
            )

        try:
            config = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return _as_evaluation_result(
                _failed_result(
                    threshold=0.0,
                    status=QualityStatus.FAILED,
                    recommendation=QualityRecommendation.GENERATION_REJECTED,
                    threshold_outcome=QualityThresholdOutcome.FAIL,
                    findings=(
                        QualityFinding(
                            severity=QualityFindingSeverity.ERROR,
                            reason_code=QualityFailureCategory.QUALITY_CONFIGURATION_INVALID.value,
                            score_impact=1.0,
                            details={},
                        ),
                    ),
                    diagnostics={"loaded": True},
                    failure_category=QualityFailureCategory.QUALITY_CONFIGURATION_INVALID.value,
                    reason_code=QualityFailureCategory.QUALITY_CONFIGURATION_INVALID.value,
                )
            )

        threshold = float(config.generation.quality_threshold)

        if not validation.passed:
            return _as_evaluation_result(
                _failed_result(
                    threshold=threshold,
                    status=QualityStatus.FAILED,
                    recommendation=QualityRecommendation.GENERATION_REJECTED,
                    threshold_outcome=QualityThresholdOutcome.FAIL,
                    findings=(
                        QualityFinding(
                            severity=QualityFindingSeverity.ERROR,
                            reason_code=QualityFailureCategory.QUALITY_INPUT_INVALID.value,
                            score_impact=1.0,
                            details={"validation_status": validation.status},
                        ),
                    ),
                    diagnostics={
                        "sample_count": validation.sample_count,
                        "validation_passed": validation.passed,
                    },
                    failure_category=QualityFailureCategory.QUALITY_INPUT_INVALID.value,
                    reason_code=QualityFailureCategory.QUALITY_INPUT_INVALID.value,
                )
            )

        try:
            sample_count = len(request.sample_references)
            unique_samples = len(set(request.sample_references))
            source_diversity = len({_source_key(ref) for ref in request.sample_references})
            enrollment_count = len(request.enrollment_references)
            prepared_count = len(request.prepared_enrollment_inputs)
            metadata_present = int(bool(request.context.correlation_id or request.context.request_id))

            min_samples = max(config.generation.min_sample_count, 1)

            breakdown = QualityScoreBreakdown(
                sample_count_score=_clamp(sample_count / min_samples),
                sample_diversity_score=_clamp(unique_samples / sample_count if sample_count > 0 else 0.0),
                source_diversity_score=_clamp(source_diversity / 2.0),
                enrollment_completeness_score=_clamp(1.0 if enrollment_count > 0 else 0.6),
                metadata_completeness_score=_clamp(1.0 if metadata_present else 0.8),
                prepared_input_score=_clamp(1.0 if prepared_count > 0 else 0.7),
            )

            overall_score = _compute_overall_score(breakdown)
            findings = _quality_findings(
                sample_count=sample_count,
                min_samples=min_samples,
                sample_diversity=breakdown.sample_diversity_score,
                source_diversity=breakdown.source_diversity_score,
                enrollment_count=enrollment_count,
                metadata_present=bool(metadata_present),
                threshold=threshold,
                overall_score=overall_score,
            )
            status = _quality_status(overall_score=overall_score, threshold=threshold)
            threshold_outcome = _threshold_outcome(
                overall_score=overall_score,
                threshold=threshold,
                findings=findings,
            )
            recommendation = _recommendation(status=status, outcome=threshold_outcome)
            failure_category = (
                QualityFailureCategory.QUALITY_THRESHOLD_NOT_MET.value
                if threshold_outcome is QualityThresholdOutcome.FAIL
                else ""
            )
            reason_code = _primary_reason_code(findings, threshold_outcome)

            result = QualityScoreResult(
                overall_score=overall_score,
                breakdown=breakdown,
                status=status,
                findings=findings,
                recommendation=recommendation,
                threshold_outcome=threshold_outcome,
                diagnostics={
                    "sample_count": sample_count,
                    "unique_sample_count": unique_samples,
                    "source_diversity_count": source_diversity,
                    "enrollment_ref_count": enrollment_count,
                    "prepared_input_count": prepared_count,
                    "finding_count": len(findings),
                    "threshold": threshold,
                },
                failure_category=failure_category,
                reason_code=reason_code,
                passed=threshold_outcome in {
                    QualityThresholdOutcome.PASS,
                    QualityThresholdOutcome.PASS_WITH_WARNING,
                },
            )
            return _as_evaluation_result(result)
        except Exception:
            return _as_evaluation_result(
                _internal_error_result(
                    reason_code=QualityFailureCategory.QUALITY_INTERNAL_ERROR.value,
                    diagnostics={"loaded": True},
                )
            )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        if not self._loaded:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("quality_scoring_not_loaded",),
                details={"loaded": False},
            )

        try:
            _ = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("quality_configuration_invalid",),
                details={"loaded": True},
            )

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("quality_scoring_ready",),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


def _as_evaluation_result(result: QualityScoreResult) -> QualityEvaluationResult:
    return QualityEvaluationResult(
        passed=result.passed,
        reason_code=result.reason_code,
        score=result.overall_score,
        threshold=float(result.diagnostics.get("threshold", result.overall_score)),
        findings=tuple(finding.reason_code for finding in result.findings),
        status=result.status.value,
        recommendation=result.recommendation.value,
        threshold_outcome=result.threshold_outcome.value,
        score_breakdown={
            "sample_count_score": result.breakdown.sample_count_score,
            "sample_diversity_score": result.breakdown.sample_diversity_score,
            "source_diversity_score": result.breakdown.source_diversity_score,
            "enrollment_completeness_score": result.breakdown.enrollment_completeness_score,
            "metadata_completeness_score": result.breakdown.metadata_completeness_score,
            "prepared_input_score": result.breakdown.prepared_input_score,
        },
        diagnostics=result.diagnostics,
        failure_category=result.failure_category,
    )


def _failed_result(
    *,
    threshold: float,
    status: QualityStatus,
    recommendation: QualityRecommendation,
    threshold_outcome: QualityThresholdOutcome,
    findings: tuple[QualityFinding, ...],
    diagnostics: dict[str, bool | int | float | str | None],
    failure_category: str,
    reason_code: str,
) -> QualityScoreResult:
    return QualityScoreResult(
        overall_score=0.0,
        breakdown=QualityScoreBreakdown(
            sample_count_score=0.0,
            sample_diversity_score=0.0,
            source_diversity_score=0.0,
            enrollment_completeness_score=0.0,
            metadata_completeness_score=0.0,
            prepared_input_score=0.0,
        ),
        status=status,
        findings=findings,
        recommendation=recommendation,
        threshold_outcome=threshold_outcome,
        diagnostics={**diagnostics, "threshold": threshold},
        failure_category=failure_category,
        reason_code=reason_code,
        passed=False,
    )


def _internal_error_result(
    *,
    reason_code: str,
    diagnostics: dict[str, bool | int | float | str | None],
) -> QualityScoreResult:
    return _failed_result(
        threshold=0.0,
        status=QualityStatus.FAILED,
        recommendation=QualityRecommendation.GENERATION_REJECTED,
        threshold_outcome=QualityThresholdOutcome.FAIL,
        findings=(
            QualityFinding(
                severity=QualityFindingSeverity.ERROR,
                reason_code=QualityFailureCategory.QUALITY_INTERNAL_ERROR.value,
                score_impact=1.0,
                details={},
            ),
        ),
        diagnostics=diagnostics,
        failure_category=QualityFailureCategory.QUALITY_INTERNAL_ERROR.value,
        reason_code=reason_code,
    )


def _compute_overall_score(breakdown: QualityScoreBreakdown) -> float:
    weighted = (
        0.30 * breakdown.sample_count_score
        + 0.20 * breakdown.sample_diversity_score
        + 0.10 * breakdown.source_diversity_score
        + 0.15 * breakdown.enrollment_completeness_score
        + 0.10 * breakdown.metadata_completeness_score
        + 0.15 * breakdown.prepared_input_score
    )
    return round(_clamp(weighted), 4)


def _quality_status(*, overall_score: float, threshold: float) -> QualityStatus:
    if overall_score >= max(threshold + 0.2, 0.9):
        return QualityStatus.EXCELLENT
    if overall_score >= max(threshold + 0.05, 0.75):
        return QualityStatus.ACCEPTABLE
    if overall_score >= threshold:
        return QualityStatus.WARNING
    if overall_score >= max(threshold - 0.15, 0.0):
        return QualityStatus.POOR
    return QualityStatus.FAILED


def _threshold_outcome(
    *,
    overall_score: float,
    threshold: float,
    findings: tuple[QualityFinding, ...],
) -> QualityThresholdOutcome:
    if overall_score < threshold:
        return QualityThresholdOutcome.FAIL
    has_warning = any(finding.severity is QualityFindingSeverity.WARNING for finding in findings)
    if has_warning:
        return QualityThresholdOutcome.PASS_WITH_WARNING
    return QualityThresholdOutcome.PASS


def _recommendation(*, status: QualityStatus, outcome: QualityThresholdOutcome) -> QualityRecommendation:
    if outcome is QualityThresholdOutcome.PASS:
        if status is QualityStatus.EXCELLENT:
            return QualityRecommendation.GENERATION_RECOMMENDED
        return QualityRecommendation.GENERATION_ALLOWED
    if outcome is QualityThresholdOutcome.PASS_WITH_WARNING:
        return QualityRecommendation.GENERATION_WARNING
    return QualityRecommendation.GENERATION_REJECTED


def _primary_reason_code(
    findings: tuple[QualityFinding, ...],
    outcome: QualityThresholdOutcome,
) -> str:
    for finding in findings:
        if finding.severity is QualityFindingSeverity.ERROR:
            return finding.reason_code
    for finding in findings:
        if finding.severity is QualityFindingSeverity.WARNING:
            return finding.reason_code
    if outcome is QualityThresholdOutcome.FAIL:
        return QualityFailureCategory.QUALITY_THRESHOLD_NOT_MET.value
    return "quality_scoring_ready"


def _quality_findings(
    *,
    sample_count: int,
    min_samples: int,
    sample_diversity: float,
    source_diversity: float,
    enrollment_count: int,
    metadata_present: bool,
    threshold: float,
    overall_score: float,
) -> tuple[QualityFinding, ...]:
    findings: list[QualityFinding] = []
    if sample_count <= max(1, min_samples // 2):
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.WARNING,
                reason_code="low_sample_count",
                score_impact=0.20,
                details={"sample_count": sample_count},
            )
        )
    if sample_diversity < 0.75:
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.WARNING,
                reason_code="insufficient_sample_diversity",
                score_impact=0.15,
                details={"sample_diversity_score": round(sample_diversity, 4)},
            )
        )
    if source_diversity < 0.5:
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.WARNING,
                reason_code="limited_source_diversity",
                score_impact=0.10,
                details={"source_diversity_score": round(source_diversity, 4)},
            )
        )
    if enrollment_count == 0:
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.WARNING,
                reason_code="enrollment_incomplete",
                score_impact=0.15,
                details={},
            )
        )
    if not metadata_present:
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.INFO,
                reason_code="metadata_incomplete",
                score_impact=0.05,
                details={},
            )
        )
    if overall_score < threshold:
        findings.append(
            QualityFinding(
                severity=QualityFindingSeverity.ERROR,
                reason_code=QualityFailureCategory.QUALITY_THRESHOLD_NOT_MET.value,
                score_impact=1.0,
                details={"score": round(overall_score, 4), "threshold": threshold},
            )
        )

    return tuple(findings)


def _source_key(reference: str) -> str:
    normalized = reference.strip()
    if ":" in normalized:
        return normalized.split(":", 1)[0].lower()
    if "_" in normalized:
        return normalized.split("_", 1)[0].lower()
    return "default"


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))