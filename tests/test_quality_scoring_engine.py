from __future__ import annotations

import pytest

from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityValidator
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceEngine
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.generation_orchestrator import (
    GenerationOrchestrator,
    GenerationRequest,
    ModelArtifactPayload,
    ModelExecutionResult,
    QualityEvaluationResult,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.quality_scoring import QualityScoringEngineProvider
from custom_components.voice_identity.sample_validation import SampleValidationPipelineProvider
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistry
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_artifact_persistence import _SpyStorageProvider
from tests.test_configuration_manager import FakeConfigEntry
from tests.test_voiceprint_registry import _FakeStore


def _config_manager(
    *,
    min_sample_count: int = 2,
    max_sample_count: int = 12,
    quality_threshold: float = 0.75,
) -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(
        FakeConfigEntry(
            data={
                "generation": {
                    "min_sample_count": min_sample_count,
                    "max_sample_count": max_sample_count,
                    "quality_threshold": quality_threshold,
                    "supported_models": ["ecapa_v1"],
                    "model_preference": "ecapa_v1",
                }
            }
        )
    )
    return manager


def _request(
    *,
    sample_references: tuple[str, ...],
    enrollment_references: tuple[str, ...] = ("enroll:mic:1",),
    prepared_enrollment_inputs: tuple[str, ...] = ("prepared:1",),
    correlation_id: str | None = "corr_1",
    request_id: str | None = "req_1",
) -> GenerationRequest:
    return GenerationRequest.create(
        subject_id="person_001",
        sample_references=sample_references,
        source="concierge",
        enrollment_references=enrollment_references,
        prepared_enrollment_inputs=prepared_enrollment_inputs,
        model_preference="ecapa_v1",
        timeout_seconds=5.0,
        correlation_id=correlation_id,
        request_id=request_id,
    )


def _high_quality_request() -> GenerationRequest:
    return _request(
        sample_references=(
            "mic:sample_1",
            "phone:sample_2",
            "satellite:sample_3",
            "mic:sample_4",
        ),
        enrollment_references=("enroll:mic:1", "enroll:phone:2"),
        prepared_enrollment_inputs=("prepared:1", "prepared:2"),
        correlation_id="corr_abc",
        request_id="req_abc",
    )


class _ModelProvider:
    async def generate(self, *, request, validation, quality) -> ModelExecutionResult:
        _ = validation
        _ = quality
        suffix = request.identifiers.generation_id[-6:]
        return ModelExecutionResult(
            success=True,
            reason_code="model_ready",
            artifact=ModelArtifactPayload(
                voiceprint_id=f"vp_{suffix}",
                artifact_id=f"artifact_{suffix}",
                encrypted_payload=b"ciphertext",
                payload_format_version=1,
                encryption_scheme="aes_gcm_v1",
                key_reference="key_v1",
                model_name="ecapa_v1",
                model_version="v1",
                schema_version=1,
            ),
            diagnostics={"provider_ready": True},
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_model_ready",),
            details={"loaded": True},
        )


@pytest.mark.asyncio
async def test_engine_initialization() -> None:
    engine = QualityScoringEngineProvider.create(config_manager=_config_manager())
    health = await engine.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("quality_scoring_ready",)


@pytest.mark.asyncio
async def test_quality_score_generation() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _high_quality_request()

    validation_result = await validation.validate(request)
    quality_result = await engine.score(request=request, validation=validation_result)

    assert quality_result.score is not None
    assert quality_result.score_breakdown


@pytest.mark.asyncio
async def test_excellent_quality_path() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)

    result = await engine.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )

    assert result.status in {"excellent", "acceptable"}
    assert result.threshold_outcome in {"pass", "pass_with_warning"}


@pytest.mark.asyncio
async def test_acceptable_quality_path() -> None:
    manager = _config_manager(quality_threshold=0.6)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _request(sample_references=("mic:sample_1", "mic:sample_2", "phone:sample_3"))

    result = await engine.score(request=request, validation=await validation.validate(request))

    assert result.status in {"acceptable", "warning", "excellent"}


@pytest.mark.asyncio
async def test_warning_quality_path() -> None:
    manager = _config_manager(min_sample_count=2, quality_threshold=0.6)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _request(
        sample_references=("mic:sample_1", "mic:sample_2"),
        enrollment_references=(),
    )

    result = await engine.score(request=request, validation=await validation.validate(request))

    assert result.threshold_outcome == "pass_with_warning"
    assert "enrollment_incomplete" in result.findings


@pytest.mark.asyncio
async def test_failed_quality_path() -> None:
    manager = _config_manager(min_sample_count=2, quality_threshold=0.95)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _request(sample_references=("mic:sample_1", "mic:sample_2"), enrollment_references=())

    result = await engine.score(request=request, validation=await validation.validate(request))

    assert result.passed is False
    assert result.threshold_outcome == "fail"


@pytest.mark.asyncio
async def test_threshold_evaluation_and_outcomes() -> None:
    manager = _config_manager(quality_threshold=0.75)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)

    pass_result = await engine.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )
    warning_request = _request(sample_references=("mic:sample_1", "mic:sample_2"), enrollment_references=())
    warning_result = await engine.score(
        request=warning_request,
        validation=await validation.validate(warning_request),
    )

    assert pass_result.threshold_outcome in {"pass", "pass_with_warning"}
    assert warning_result.threshold_outcome in {"pass_with_warning", "fail"}


@pytest.mark.asyncio
async def test_quality_findings_generation() -> None:
    manager = _config_manager(quality_threshold=0.8)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _request(sample_references=("mic:sample_1", "mic:sample_2"), enrollment_references=())

    result = await engine.score(request=request, validation=await validation.validate(request))

    assert isinstance(result.findings, tuple)
    assert all(isinstance(code, str) for code in result.findings)


@pytest.mark.asyncio
async def test_score_breakdown_generation() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _high_quality_request()

    result = await engine.score(request=request, validation=await validation.validate(request))

    expected = {
        "sample_count_score",
        "sample_diversity_score",
        "source_diversity_score",
        "enrollment_completeness_score",
        "metadata_completeness_score",
        "prepared_input_score",
    }
    assert set(result.score_breakdown.keys()) == expected


@pytest.mark.asyncio
async def test_deterministic_scoring_behavior() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _high_quality_request()
    validation_result = await validation.validate(request)

    result_one = await engine.score(request=request, validation=validation_result)
    result_two = await engine.score(request=request, validation=validation_result)

    assert result_one.score == result_two.score
    assert result_one.findings == result_two.findings
    assert result_one.threshold_outcome == result_two.threshold_outcome


@pytest.mark.asyncio
async def test_failure_taxonomy_mapping() -> None:
    manager = _config_manager(quality_threshold=0.99)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    request = _request(sample_references=("mic:sample_1", "mic:sample_2"), enrollment_references=())

    result = await engine.score(request=request, validation=await validation.validate(request))

    assert result.failure_category == "quality_threshold_not_met"


@pytest.mark.asyncio
async def test_internal_error_mapping(monkeypatch) -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)

    def _boom(_):
        raise RuntimeError("boom_internal")

    monkeypatch.setattr(
        "custom_components.voice_identity.quality_scoring._compute_overall_score",
        _boom,
    )

    request = _high_quality_request()
    result = await engine.score(request=request, validation=await validation.validate(request))

    assert result.passed is False
    assert result.failure_category == "quality_internal_error"
    assert result.reason_code == "quality_internal_error"


@pytest.mark.asyncio
async def test_safe_diagnostics_generation() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    result = await engine.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )

    assert "sample_count" in result.diagnostics
    assert "finding_count" in result.diagnostics


@pytest.mark.asyncio
async def test_no_payload_leakage() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)
    result = await engine.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )
    rendered = str(result)
    assert "ciphertext" not in rendered
    assert "payload" not in rendered


@pytest.mark.asyncio
async def test_no_raw_exception_leakage(monkeypatch) -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    engine = QualityScoringEngineProvider.create(config_manager=manager)

    def _boom(_):
        raise RuntimeError("super_secret_exception")

    monkeypatch.setattr(
        "custom_components.voice_identity.quality_scoring._compute_overall_score",
        _boom,
    )

    result = await engine.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )
    rendered = str(result)
    assert "super_secret_exception" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.asyncio
async def test_integration_with_vi110_generation_orchestrator() -> None:
    manager = _config_manager(quality_threshold=0.6)
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    quality = QualityScoringEngineProvider.create(config_manager=manager)
    storage = _SpyStorageProvider()
    registry = VoiceprintRegistry(store=_FakeStore(), storage_provider=storage)
    await registry.async_load()
    lifecycle = VoiceprintLifecycleManager.create(registry=registry)
    revision = VoiceprintRevisionManager.create(registry=registry, lifecycle_manager=lifecycle)
    persistence = ArtifactPersistenceEngine.create(
        storage_provider=storage,
        registry=registry,
        lifecycle_manager=lifecycle,
        revision_manager=revision,
    )
    integrity = ArtifactIntegrityValidator.create(
        storage_provider=storage,
        registry=registry,
        revision_manager=revision,
    )

    orchestrator = GenerationOrchestrator.create(
        config_manager=manager,
        validation_pipeline=validation,
        quality_engine=quality,
        model_provider=_ModelProvider(),
        persistence_engine=persistence,
        integrity_validator=integrity,
    )

    result = await orchestrator.generate_voiceprint(_high_quality_request())
    assert result.success is True
    assert result.quality_summary.status in {"excellent", "acceptable", "warning"}


@pytest.mark.asyncio
async def test_integration_with_vi111_validation_outputs() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    quality = QualityScoringEngineProvider.create(config_manager=manager)
    invalid_request = _request(sample_references=())

    validation_result = await validation.validate(invalid_request)
    quality_result = await quality.score(request=invalid_request, validation=validation_result)

    assert validation_result.passed is False
    assert quality_result.passed is False
    assert quality_result.failure_category == "quality_input_invalid"


@pytest.mark.asyncio
async def test_validation_logic_remains_in_vi111() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    quality = QualityScoringEngineProvider.create(config_manager=manager)
    invalid_request = _request(sample_references=())

    validation_result = await validation.validate(invalid_request)
    quality_result = await quality.score(request=invalid_request, validation=validation_result)

    assert "sample_reference_missing" in validation_result.findings
    assert "sample_reference_missing" not in quality_result.findings
    assert quality_result.failure_category == "quality_input_invalid"


@pytest.mark.asyncio
async def test_vi113_compatibility_output_contract() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    quality = QualityScoringEngineProvider.create(config_manager=manager)

    result = await quality.score(
        request=_high_quality_request(),
        validation=await validation.validate(_high_quality_request()),
    )

    assert result.status in {"excellent", "acceptable", "warning", "poor", "failed"}
    assert result.recommendation in {
        "generation_recommended",
        "generation_allowed",
        "generation_warning",
        "generation_rejected",
    }
    assert result.threshold_outcome in {"pass", "pass_with_warning", "fail"}
