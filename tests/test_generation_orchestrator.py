from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from custom_components.voice_identity.artifact_integrity import IntegrityFinding, IntegrityFindingType, IntegritySeverity
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceStorageError
from custom_components.voice_identity.generation_orchestrator import (
    ContractValidationPipeline,
    GenerationFailureCategory,
    GenerationOrchestrator,
    GenerationRequest,
    GenerationStatus,
    GenerationSuccessResult,
    ModelArtifactPayload,
    ModelExecutionResult,
    QualityEvaluationResult,
    SampleValidationResult,
)
from custom_components.voice_identity.health_state import HealthState
from tests.test_artifact_integrity import _build_stack
from tests.test_configuration_manager import FakeConfigEntry
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager


@dataclass
class _ValidationPipeline:
    passed: bool = True
    reason_code: str = "validation_passed"
    sample_count: int = 6
    findings: tuple[str, ...] = ()
    raises: bool = False
    delay_seconds: float = 0.0

    async def validate(self, request: GenerationRequest) -> SampleValidationResult:
        _ = request
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.raises:
            raise RuntimeError("boom")
        return SampleValidationResult(
            passed=self.passed,
            reason_code=self.reason_code,
            sample_count=self.sample_count,
            findings=self.findings,
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_validation_ready",),
            details={"loaded": True},
        )


@dataclass
class _QualityEngine:
    passed: bool = True
    reason_code: str = "quality_ready"
    score: float | None = 0.9
    threshold: float | None = 0.75
    findings: tuple[str, ...] = ()
    failure_category: str = ""
    raises: bool = False

    async def score(self, *, request: GenerationRequest, validation: SampleValidationResult) -> QualityEvaluationResult:
        _ = request
        _ = validation
        if self.raises:
            raise RuntimeError("boom")
        return QualityEvaluationResult(
            passed=self.passed,
            reason_code=self.reason_code,
            score=self.score,
            threshold=self.threshold,
            findings=self.findings,
            failure_category=self.failure_category,
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_quality_ready",),
            details={"loaded": True},
        )


@dataclass
class _ModelProvider:
    success: bool = True
    reason_code: str = "model_execution_ready"
    model_name: str = "ecapa_v1"
    raises: bool = False

    async def generate(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
        quality: QualityEvaluationResult,
    ) -> ModelExecutionResult:
        _ = validation
        _ = quality
        if self.raises:
            raise RuntimeError("boom")
        if not self.success:
            return ModelExecutionResult(
                success=False,
                reason_code=self.reason_code,
                artifact=None,
                diagnostics={"provider_ready": False},
            )

        suffix = request.identifiers.generation_id[-6:]
        artifact = ModelArtifactPayload(
            voiceprint_id=f"vp_{suffix}",
            artifact_id=f"artifact_{suffix}",
            encrypted_payload=b"ciphertext",
            payload_format_version=1,
            encryption_scheme="aes_gcm_v1",
            key_reference="key_v1",
            model_name=self.model_name,
            model_version="v1",
            schema_version=1,
        )
        return ModelExecutionResult(
            success=True,
            reason_code=self.reason_code,
            artifact=artifact,
            diagnostics={"provider_ready": True},
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_model_ready",),
            details={"loaded": True},
        )


class _FailingPersistenceEngine:
    async def persist_artifact(self, request):
        _ = request
        raise ArtifactPersistenceStorageError("artifact_persistence_save_failed")

    async def validate_health(self):
        from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceHealth

        return ArtifactPersistenceHealth(
            state=HealthState.HEALTHY,
            reason_codes=("artifact_persistence_ready",),
            details={"loaded": True},
        )


class _FailingIntegrityValidator:
    async def validate_voiceprint(self, voiceprint_id):
        _ = voiceprint_id
        return type(
            "IntegrityResult",
            (),
            {
                "status": IntegritySeverity.CORRUPTED,
                "findings": (
                    IntegrityFinding(
                        status=IntegritySeverity.CORRUPTED.value,
                        finding_type=IntegrityFindingType.ARTIFACT,
                        severity=IntegritySeverity.CORRUPTED,
                        reason_code="digest_mismatch",
                        validation_timestamp="2026-01-01T00:00:00+00:00",
                        affected_artifact_id="artifact_id",
                        affected_revision_id="vp_id",
                        details={},
                    ),
                ),
            },
        )()

    async def validate_health(self):
        from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityHealth

        return ArtifactIntegrityHealth(
            state=HealthState.HEALTHY,
            reason_codes=("artifact_integrity_ready",),
            details={"loaded": True, "finding_count": 0},
        )


def _config_manager() -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(FakeConfigEntry())
    return manager


def _request(**overrides) -> GenerationRequest:
    base = GenerationRequest.create(
        subject_id="person_001",
        sample_references=("sample_1", "sample_2", "sample_3", "sample_4", "sample_5", "sample_6"),
        source="concierge",
        enrollment_references=("enroll_1",),
        prepared_enrollment_inputs=("prepared_1",),
        model_preference="ecapa_v1",
        timeout_seconds=3.0,
    )
    if not overrides:
        return base
    return GenerationRequest(
        identifiers=overrides.get("identifiers", base.identifiers),
        context=overrides.get("context", base.context),
        options=overrides.get("options", base.options),
        sample_references=overrides.get("sample_references", base.sample_references),
        enrollment_references=overrides.get("enrollment_references", base.enrollment_references),
        prepared_enrollment_inputs=overrides.get("prepared_enrollment_inputs", base.prepared_enrollment_inputs),
        requested_at=overrides.get("requested_at", base.requested_at),
    )


async def _build_orchestrator(
    *,
    validation: _ValidationPipeline | None = None,
    quality: _QualityEngine | None = None,
    model: _ModelProvider | None = None,
    persistence_engine=None,
    integrity_validator=None,
):
    _, _, _, _, persistence, validator = await _build_stack()
    return GenerationOrchestrator.create(
        config_manager=_config_manager(),
        validation_pipeline=validation or _ValidationPipeline(),
        quality_engine=quality or _QualityEngine(),
        model_provider=model or _ModelProvider(),
        persistence_engine=persistence_engine or persistence,
        integrity_validator=integrity_validator or validator,
    )


@pytest.mark.asyncio
async def test_orchestrator_initialization_and_health() -> None:
    orchestrator = await _build_orchestrator()
    health = await orchestrator.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("generation_orchestrator_ready",)


def test_generation_request_creation() -> None:
    request = _request()
    assert request.identifiers.generation_id.startswith("gen_")
    assert request.context.source == "concierge"
    assert len(request.sample_references) == 6


@pytest.mark.asyncio
async def test_contract_validation_pipeline_is_policy_free() -> None:
    pipeline = ContractValidationPipeline()
    request = _request(sample_references=())
    result = await pipeline.validate(request)

    assert result.passed is True
    assert result.reason_code == "validation_contract_ready"
    assert result.sample_count == 0
    assert result.findings == ()


@pytest.mark.asyncio
async def test_successful_workflow_orchestration_and_status_progression() -> None:
    orchestrator = await _build_orchestrator()
    request = _request()

    result = await orchestrator.generate_voiceprint(request)
    status = await orchestrator.get_status(request.identifiers.generation_id)

    assert isinstance(result, GenerationSuccessResult)
    assert result.status is GenerationStatus.COMPLETED
    assert result.validation_summary.passed is True
    assert result.quality_summary.passed is True
    assert result.integrity_summary.passed is True
    assert status is not None
    assert status.current_status is GenerationStatus.COMPLETED
    assert tuple(event.status for event in status.history) == (
        GenerationStatus.QUEUED,
        GenerationStatus.VALIDATING,
        GenerationStatus.QUALITY_SCORING,
        GenerationStatus.GENERATING,
        GenerationStatus.PERSISTING,
        GenerationStatus.VALIDATING_INTEGRITY,
        GenerationStatus.COMPLETED,
    )


@pytest.mark.asyncio
async def test_validation_failure_handling() -> None:
    orchestrator = await _build_orchestrator(
        validation=_ValidationPipeline(passed=False, reason_code="validation_failed", sample_count=1),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_insufficient_samples_failure_taxonomy() -> None:
    orchestrator = await _build_orchestrator(
        validation=_ValidationPipeline(
            passed=False,
            reason_code="insufficient_samples",
            sample_count=0,
            findings=("insufficient_samples",),
        ),
    )
    result = await orchestrator.generate_voiceprint(_request(sample_references=()))
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.INSUFFICIENT_SAMPLES


@pytest.mark.asyncio
async def test_quality_failure_handling() -> None:
    orchestrator = await _build_orchestrator(
        quality=_QualityEngine(passed=False, reason_code="quality_threshold_not_met"),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.QUALITY_THRESHOLD_NOT_MET


@pytest.mark.asyncio
async def test_quality_non_threshold_failure_category_preserved() -> None:
    orchestrator = await _build_orchestrator(
        quality=_QualityEngine(
            passed=False,
            reason_code="quality_configuration_invalid",
            failure_category="quality_configuration_invalid",
        ),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.QUALITY_CONFIGURATION_INVALID


@pytest.mark.asyncio
async def test_model_failure_handling() -> None:
    orchestrator = await _build_orchestrator(
        model=_ModelProvider(success=False, reason_code="model_execution_failed"),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.MODEL_EXECUTION_FAILED


@pytest.mark.asyncio
async def test_persistence_failure_handling() -> None:
    orchestrator = await _build_orchestrator(
        persistence_engine=_FailingPersistenceEngine(),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.PERSISTENCE_FAILED
    assert result.reason_code == "generation_persistence_failed"


@pytest.mark.asyncio
async def test_integrity_failure_handling() -> None:
    orchestrator = await _build_orchestrator(
        integrity_validator=_FailingIntegrityValidator(),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.INTEGRITY_VALIDATION_FAILED


@pytest.mark.asyncio
async def test_unsupported_model_failure() -> None:
    orchestrator = await _build_orchestrator(model=_ModelProvider(model_name="ecapa_v2"))
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.UNSUPPORTED_MODEL


@pytest.mark.asyncio
async def test_timeout_failure_taxonomy() -> None:
    orchestrator = await _build_orchestrator(validation=_ValidationPipeline(delay_seconds=0.05))
    request = _request(
        options=_request().options.__class__(
            model_preference="ecapa_v1",
            timeout_seconds=0.001,
            activate=True,
        )
    )
    result = await orchestrator.generate_voiceprint(request)
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.GENERATION_TIMEOUT


@pytest.mark.asyncio
async def test_async_status_progression_with_cancel() -> None:
    orchestrator = await _build_orchestrator(validation=_ValidationPipeline(delay_seconds=0.05))
    request = _request()
    task = asyncio.create_task(orchestrator.generate_voiceprint(request))
    await asyncio.sleep(0.01)
    cancelled = await orchestrator.cancel_generation(request.identifiers.generation_id)
    result = await task

    assert cancelled is True
    assert result.success is False
    assert result.failure_category is GenerationFailureCategory.CANCELLED
    assert result.status is GenerationStatus.CANCELLED


@pytest.mark.asyncio
async def test_safe_success_result_no_payload_recording_or_secret_leakage() -> None:
    orchestrator = await _build_orchestrator()
    result = await orchestrator.generate_voiceprint(_request())
    rendered = str(result)
    assert "ciphertext" not in rendered
    assert "sample_" not in rendered
    assert "key_v1" not in rendered


@pytest.mark.asyncio
async def test_safe_failure_result_no_payload_recording_or_secret_leakage() -> None:
    orchestrator = await _build_orchestrator(model=_ModelProvider(success=False))
    result = await orchestrator.generate_voiceprint(_request())
    rendered = str(result)
    assert "ciphertext" not in rendered
    assert "sample_" not in rendered
    assert "key_v1" not in rendered


@pytest.mark.asyncio
async def test_clear_behavior() -> None:
    orchestrator = await _build_orchestrator()
    orchestrator.clear()
    assert orchestrator.cleared is True


@pytest.mark.asyncio
async def test_vi111_vi112_vi113_contract_compatibility() -> None:
    orchestrator = await _build_orchestrator(
        validation=_ValidationPipeline(),
        quality=_QualityEngine(),
        model=_ModelProvider(),
    )
    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is True


@pytest.mark.asyncio
async def test_vi114_compatibility_status_lookup() -> None:
    orchestrator = await _build_orchestrator()
    request = _request()
    _ = await orchestrator.generate_voiceprint(request)
    status = await orchestrator.get_status(request.identifiers.generation_id)
    assert status is not None
    assert status.generation_id == request.identifiers.generation_id
    assert status.current_status in {
        GenerationStatus.COMPLETED,
        GenerationStatus.FAILED,
        GenerationStatus.CANCELLED,
    }
