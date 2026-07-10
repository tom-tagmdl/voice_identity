from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityValidator
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceEngine, PersistArtifactRequest
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.generation_orchestrator import (
    GenerationOrchestrator,
    GenerationRequest,
    GenerationStatus,
    ModelExecutionResult,
    QualityEvaluationResult,
    SampleValidationResult,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.model_execution import (
    BackendExecutionRequest,
    BackendExecutionResult,
    ModelBackendExecutionError,
    ModelExecutionFailureCategory,
    ModelExecutionProviderRuntime,
    ModelProviderMetadata,
    UnavailableModelExecutionBackend,
)
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistry
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_artifact_persistence import _SpyStorageProvider
from tests.test_configuration_manager import FakeConfigEntry
from tests.test_voiceprint_registry import _FakeStore


def _config_manager(
    *,
    model_preference: str = "ecapa_v1",
    supported_models: tuple[str, ...] = ("ecapa_v1",),
) -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(
        FakeConfigEntry(
            data={
                "generation": {
                    "model_preference": model_preference,
                    "min_sample_count": 2,
                    "max_sample_count": 12,
                    "quality_threshold": 0.75,
                    "supported_models": list(supported_models),
                }
            }
        )
    )
    return manager


def _request(
    *,
    sample_references: tuple[str, ...] = ("sample_1", "sample_2"),
    prepared_enrollment_inputs: tuple[str, ...] = ("prepared_1",),
    model_preference: str | None = "ecapa_v1",
    timeout_seconds: float | None = 1.0,
) -> GenerationRequest:
    return GenerationRequest.create(
        subject_id="person_001",
        sample_references=sample_references,
        source="concierge",
        enrollment_references=("enroll_1",),
        prepared_enrollment_inputs=prepared_enrollment_inputs,
        model_preference=model_preference,
        timeout_seconds=timeout_seconds,
    )


@dataclass
class _ValidationPass:
    passed: bool = True

    async def validate(self, request: GenerationRequest) -> SampleValidationResult:
        return SampleValidationResult(
            passed=self.passed,
            reason_code="validation_ready" if self.passed else "validation_failed",
            sample_count=len(request.sample_references),
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_validation_ready",),
            details={"loaded": True},
        )


@dataclass
class _QualityPass:
    passed: bool = True

    async def score(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
    ) -> QualityEvaluationResult:
        _ = request
        _ = validation
        return QualityEvaluationResult(
            passed=self.passed,
            reason_code="quality_ready" if self.passed else "quality_threshold_not_met",
            score=0.9 if self.passed else 0.3,
            threshold=0.75,
            findings=(),
        )

    async def validate_health(self):
        from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_quality_ready",),
            details={"loaded": True},
        )


class _ReadyBackend:
    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        raise_reason: str | None = None,
        raise_internal: bool = False,
        invalid_output: bool = False,
        provider_name: str = "test_backend",
        provider_version: str = "1",
    ) -> None:
        self._delay_seconds = delay_seconds
        self._raise_reason = raise_reason
        self._raise_internal = raise_internal
        self._invalid_output = invalid_output
        self._provider_name = provider_name
        self._provider_version = provider_version

    @property
    def metadata(self) -> ModelProviderMetadata:
        return ModelProviderMetadata(
            provider_name=self._provider_name,
            provider_version=self._provider_version,
            supported_models=("ecapa_v1",),
            supported_representation_formats=("encrypted_representation_v1",),
            available=True,
        )

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        _ = request
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._raise_reason is not None:
            raise ModelBackendExecutionError(self._raise_reason)
        if self._raise_internal:
            raise RuntimeError("C:/secret/token/raw_exception")
        if self._invalid_output:
            return BackendExecutionResult(
                encrypted_payload=b"",
                payload_format_version=0,
                encryption_scheme="invalid scheme",
                key_reference="invalid key",
                model_version="model version",
                schema_version=0,
                representation_format="invalid format",
            )
        return BackendExecutionResult(
            encrypted_payload=b"enc_payload_v1",
            payload_format_version=1,
            encryption_scheme="aes_gcm_v1",
            key_reference="key_ref_v1",
            model_version="v1",
            schema_version=1,
            representation_format="encrypted_representation_v1",
            provider_confidence=0.91,
        )


@pytest.mark.asyncio
async def test_provider_initialization() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager())
    assert isinstance(provider, ModelExecutionProviderRuntime)


@pytest.mark.asyncio
async def test_provider_readiness_health_unavailable_by_default() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager())
    health = await provider.validate_health()
    assert health.state is HealthState.UNAVAILABLE
    assert health.reason_codes == ("model_provider_unavailable",)


@pytest.mark.asyncio
async def test_provider_readiness_health_ready_with_backend() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(),
    )
    health = await provider.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("model_execution_ready",)


@pytest.mark.asyncio
async def test_successful_model_execution_contract_with_test_backend() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is True
    assert result.reason_code == "model_execution_ready"
    assert result.artifact is not None
    assert result.artifact.model_name == "ecapa_v1"
    assert result.artifact.encryption_scheme == "aes_gcm_v1"


@pytest.mark.asyncio
async def test_unsupported_model_handling() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(supported_models=("ecapa_v1",)),
        backend=_ReadyBackend(),
    )
    request = _request(model_preference="ecapa_v2")
    result = await provider.generate(
        request=request,
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.UNSUPPORTED_MODEL.value


@pytest.mark.asyncio
async def test_provider_not_loaded_handling() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    provider.clear()
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_PROVIDER_NOT_LOADED.value


@pytest.mark.asyncio
async def test_provider_unavailable_handling() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=UnavailableModelExecutionBackend(),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_PROVIDER_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_invalid_model_input_handling() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    result = await provider.generate(
        request=_request(sample_references=()),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=0),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_INPUT_INVALID.value


@pytest.mark.asyncio
async def test_model_execution_failure_mapping() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(raise_reason="model_execution_failed"),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_EXECUTION_FAILED.value


@pytest.mark.asyncio
async def test_model_timeout_mapping() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(delay_seconds=0.05),
    )
    result = await provider.generate(
        request=_request(timeout_seconds=0.001),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_TIMEOUT.value


@pytest.mark.asyncio
async def test_invalid_model_output_handling() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(invalid_output=True),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_OUTPUT_INVALID.value


@pytest.mark.asyncio
async def test_internal_error_mapping() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(raise_internal=True),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_INTERNAL_ERROR.value


@pytest.mark.asyncio
async def test_safe_failure_result_creation() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(raise_reason="MODEL EXECUTION FAILED"),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_EXECUTION_FAILED.value


@pytest.mark.asyncio
async def test_safe_success_result_creation() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert isinstance(result, ModelExecutionResult)
    assert result.success is True
    assert result.artifact is not None
    assert result.diagnostics["provider"] == "test_backend"


@pytest.mark.asyncio
async def test_representation_output_compatibility_with_vi108() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is True
    assert result.artifact is not None
    persist_request = PersistArtifactRequest(
        voiceprint_id=result.artifact.voiceprint_id,
        artifact_id=result.artifact.artifact_id,
        subject_id="person_001",
        current_voiceprint_id=None,
        encrypted=True,
        encrypted_payload=result.artifact.encrypted_payload,
        payload_format_version=result.artifact.payload_format_version,
        encryption_scheme=result.artifact.encryption_scheme,
        key_reference=result.artifact.key_reference,
        model_name=result.artifact.model_name,
        model_version=result.artifact.model_version,
        schema_version=result.artifact.schema_version,
    )
    assert persist_request.encrypted is True


@pytest.mark.asyncio
async def test_no_validation_logic_duplication_from_vi111() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(
            passed=False,
            reason_code="sample_reference_missing",
            sample_count=0,
            findings=("sample_reference_missing",),
        ),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_INPUT_INVALID.value


@pytest.mark.asyncio
async def test_no_quality_scoring_duplication_from_vi112() -> None:
    provider = ModelExecutionProviderRuntime.create(config_manager=_config_manager(), backend=_ReadyBackend())
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(
            passed=False,
            reason_code="quality_threshold_not_met",
            score=0.4,
            threshold=0.75,
            findings=("quality_threshold_not_met",),
        ),
    )

    assert result.success is False
    assert result.reason_code == ModelExecutionFailureCategory.MODEL_INPUT_INVALID.value


def test_no_artifact_persistence_performed_by_vi113() -> None:
    assert hasattr(ModelExecutionProviderRuntime, "generate")
    assert not hasattr(ModelExecutionProviderRuntime, "persist_artifact")


def test_no_integrity_validation_performed_by_vi113() -> None:
    assert not hasattr(ModelExecutionProviderRuntime, "validate_voiceprint")


def test_no_lifecycle_or_revision_mutation_performed_by_vi113() -> None:
    assert not hasattr(ModelExecutionProviderRuntime, "activate_record")
    assert not hasattr(ModelExecutionProviderRuntime, "coordinate_supersession")


@pytest.mark.asyncio
async def test_privacy_boundaries_no_sensitive_leakage() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(raise_internal=True),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    rendered = str(result)
    assert "C:/secret/token/raw_exception" not in rendered
    assert "sample_" not in rendered
    assert "enc_payload_v1" not in rendered


@pytest.mark.asyncio
async def test_unsafe_provider_metadata_sanitized_in_success_diagnostics() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(
            provider_name="C:/backend/secret/provider",
            provider_version="https://internal/version?token=abc",
        ),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is True
    assert result.diagnostics["provider"] == "unknown_provider"
    assert result.diagnostics["provider_version"] == "unknown_version"


@pytest.mark.asyncio
async def test_unsafe_provider_metadata_sanitized_in_failure_diagnostics() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(
            raise_reason="model_execution_failed",
            provider_name="D:/private/provider",
            provider_version="http://sensitive/internal",
        ),
    )
    result = await provider.generate(
        request=_request(),
        validation=SampleValidationResult(passed=True, reason_code="validation_ready", sample_count=2),
        quality=QualityEvaluationResult(passed=True, reason_code="quality_ready", score=0.9, threshold=0.75),
    )

    assert result.success is False
    assert result.diagnostics["provider"] == "unknown_provider"
    assert result.diagnostics["provider_version"] == "unknown_version"


@pytest.mark.asyncio
async def test_unsafe_provider_metadata_sanitized_in_health_reporting() -> None:
    provider = ModelExecutionProviderRuntime.create(
        config_manager=_config_manager(),
        backend=_ReadyBackend(
            provider_name="C:/backend/private",
            provider_version="https://sensitive/version",
        ),
    )
    health = await provider.validate_health()

    assert health.details["provider"] == "unknown_provider"
    assert health.details["provider_version"] == "unknown_version"


@pytest.mark.asyncio
async def test_integration_with_vi110_generation_orchestrator() -> None:
    manager = _config_manager()
    provider = ModelExecutionProviderRuntime.create(config_manager=manager, backend=_ReadyBackend())
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
        validation_pipeline=_ValidationPass(),
        quality_engine=_QualityPass(),
        model_provider=provider,
        persistence_engine=persistence,
        integrity_validator=integrity,
    )

    result = await orchestrator.generate_voiceprint(_request())
    assert result.success is True


@pytest.mark.asyncio
async def test_vi114_compatibility_status_lookup() -> None:
    manager = _config_manager()
    provider = ModelExecutionProviderRuntime.create(config_manager=manager, backend=_ReadyBackend())
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
        validation_pipeline=_ValidationPass(),
        quality_engine=_QualityPass(),
        model_provider=provider,
        persistence_engine=persistence,
        integrity_validator=integrity,
    )

    request = _request()
    _ = await orchestrator.generate_voiceprint(request)
    status = await orchestrator.get_status(request.identifiers.generation_id)
    assert status is not None
    assert status.current_status in {GenerationStatus.COMPLETED, GenerationStatus.FAILED, GenerationStatus.CANCELLED}
