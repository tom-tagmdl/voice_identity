from __future__ import annotations

import pytest

from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityValidator
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceEngine
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.generation_orchestrator import (
    ContractValidationPipeline,
    GenerationOrchestrator,
    GenerationRequest,
    ModelArtifactPayload,
    ModelExecutionResult,
    QualityEvaluationResult,
    SampleValidationResult,
)
from custom_components.voice_identity.sample_validation import SampleValidationPipelineProvider
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistry
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_artifact_persistence import _SpyStorageProvider
from tests.test_configuration_manager import FakeConfigEntry
from tests.test_voiceprint_registry import _FakeStore


def _config_manager(*, min_samples: int = 2, max_samples: int = 8) -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(
        FakeConfigEntry(
            data={
                "generation": {
                    "min_sample_count": min_samples,
                    "max_sample_count": max_samples,
                    "supported_models": ["ecapa_v1"],
                    "model_preference": "ecapa_v1",
                }
            }
        )
    )
    return manager


def _request(**overrides) -> GenerationRequest:
    base = GenerationRequest.create(
        subject_id="person_001",
        sample_references=("sample_1", "sample_2"),
        source="concierge",
        enrollment_references=("enroll_1",),
        prepared_enrollment_inputs=("prepared_1",),
        model_preference="ecapa_v1",
        timeout_seconds=5.0,
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


@pytest.mark.asyncio
async def test_pipeline_initialization() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    health = await pipeline.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("sample_validation_ready",)


@pytest.mark.asyncio
async def test_valid_request_validation() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request())
    assert result.passed is True
    assert result.status == "valid"


@pytest.mark.asyncio
async def test_missing_sample_references() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(sample_references=()))
    assert result.passed is False
    assert "sample_reference_missing" in result.findings


@pytest.mark.asyncio
async def test_missing_enrollment_references_warning() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(enrollment_references=()))
    assert result.passed is True
    assert result.status == "warning"
    assert "enrollment_reference_missing" in result.findings


@pytest.mark.asyncio
async def test_invalid_references() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(
        _request(sample_references=("bad/ref", "sample_2"), enrollment_references=("bad path",))
    )
    assert result.passed is False
    assert "sample_reference_invalid" in result.findings
    assert "enrollment_reference_invalid" in result.findings


@pytest.mark.asyncio
async def test_duplicate_sample_detection() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(sample_references=("sample_1", "sample_1")))
    assert result.passed is False
    assert "duplicate_samples" in result.findings


@pytest.mark.asyncio
async def test_unsupported_configuration_detection() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager(max_samples=2))
    result = await pipeline.validate(_request(sample_references=("sample_1", "sample_2", "sample_3")))
    assert result.passed is False
    assert "unsupported_configuration" in result.findings


@pytest.mark.asyncio
async def test_empty_sample_collection_handling() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager(min_samples=1))
    result = await pipeline.validate(_request(sample_references=()))
    assert result.passed is False
    assert result.reason_code in {
        "sample_reference_missing",
        "insufficient_samples",
    }


@pytest.mark.asyncio
async def test_validation_warning_scenarios() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(enrollment_references=()))
    assert result.status == "warning"
    assert result.recommend_continue is True


@pytest.mark.asyncio
async def test_validation_error_scenarios() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(sample_references=("sample_1",)))
    assert result.status == "invalid"
    assert result.highest_severity == "error"


@pytest.mark.asyncio
async def test_failure_taxonomy_mapping() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(sample_references=("sample_1", "sample_1")))
    assert result.reason_code == "duplicate_samples"


@pytest.mark.asyncio
async def test_safe_diagnostics_generation() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request())
    assert set(result.diagnostics.keys()) == {"sample_count", "finding_count", "blocking_count"}


@pytest.mark.asyncio
async def test_no_payload_leakage() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request())
    rendered = str(result)
    assert "ciphertext" not in rendered
    assert "payload" not in rendered


@pytest.mark.asyncio
async def test_no_raw_exception_leakage() -> None:
    manager = VoiceIdentityConfigurationManager()
    pipeline = SampleValidationPipelineProvider.create(config_manager=manager)
    result = await pipeline.validate(_request())
    rendered = str(result)
    assert "Traceback" not in rendered
    assert "Exception" not in rendered
    assert result.reason_code == "validation_configuration_invalid"


@pytest.mark.asyncio
async def test_internal_exception_maps_to_safe_validation_internal_error(monkeypatch) -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())

    def _boom(value: str) -> bool:
        raise RuntimeError(f"boom:{value}")

    monkeypatch.setattr(
        "custom_components.voice_identity.sample_validation._is_valid_reference",
        _boom,
    )

    result = await pipeline.validate(_request())
    rendered = str(result)

    assert result.passed is False
    assert result.status == "invalid"
    assert result.highest_severity == "error"
    assert result.failure_category == "validation_internal_error"
    assert result.reason_code == "validation_internal_error"
    assert result.findings == ("validation_internal_error",)
    assert "boom" not in rendered
    assert "Traceback" not in rendered
    assert "RuntimeError" not in rendered


@pytest.mark.asyncio
async def test_health_not_loaded() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    pipeline.clear()
    health = await pipeline.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert health.reason_codes == ("sample_validation_not_loaded",)


@pytest.mark.asyncio
async def test_vi112_compatibility_machine_readable_output() -> None:
    pipeline = SampleValidationPipelineProvider.create(config_manager=_config_manager())
    result = await pipeline.validate(_request(enrollment_references=()))
    assert isinstance(result.findings, tuple)
    assert all(isinstance(code, str) for code in result.findings)


@pytest.mark.asyncio
async def test_vi110_integration_with_real_validation_pipeline() -> None:
    class _QualityEngine:
        async def score(self, *, request: GenerationRequest, validation: SampleValidationResult) -> QualityEvaluationResult:
            _ = request
            _ = validation
            return QualityEvaluationResult(
                passed=True,
                reason_code="quality_contract_ready",
                score=None,
                threshold=None,
            )

        async def validate_health(self):
            from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

            return GenerationOrchestratorHealth(
                state=HealthState.HEALTHY,
                reason_codes=("generation_quality_ready",),
                details={"loaded": True},
            )

    class _ModelProvider:
        async def generate(
            self,
            *,
            request: GenerationRequest,
            validation: SampleValidationResult,
            quality: QualityEvaluationResult,
        ) -> ModelExecutionResult:
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
        config_manager=_config_manager(),
        validation_pipeline=SampleValidationPipelineProvider.create(config_manager=_config_manager()),
        quality_engine=_QualityEngine(),
        model_provider=_ModelProvider(),
        persistence_engine=persistence,
        integrity_validator=integrity,
    )

    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is True


@pytest.mark.asyncio
async def test_validation_logic_moved_out_of_vi110_contract_adapter() -> None:
    pipeline = ContractValidationPipeline()
    result = await pipeline.validate(_request(sample_references=()))
    assert result.passed is True
    assert result.reason_code == "validation_contract_ready"