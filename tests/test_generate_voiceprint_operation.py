from __future__ import annotations

import pytest

from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityValidator
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceEngine
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.generate_voiceprint_operation import (
    GenerateVoiceprintFailureCategory,
    GenerateVoiceprintOperation,
    GenerateVoiceprintOperationStatus,
    GenerateVoiceprintRequest,
)
from custom_components.voice_identity.generation_orchestrator import (
    GenerationFailureCategory,
    GenerationFailureResult,
    GenerationOrchestrator,
    GenerationOrchestratorHealth,
    GenerationStatus,
    GenerationStatusEvent,
    GenerationSuccessResult,
    IntegrityValidationSummary,
    QualitySummary,
    ValidationSummary,
)
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.model_execution import (
    BackendExecutionRequest,
    BackendExecutionResult,
    ModelExecutionProviderRuntime,
    ModelProviderMetadata,
)
from custom_components.voice_identity.quality_scoring import QualityScoringEngineProvider
from custom_components.voice_identity.sample_validation import SampleValidationPipelineProvider
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleManager
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistry
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionManager
from tests.test_artifact_persistence import _SpyStorageProvider
from tests.test_configuration_manager import FakeConfigEntry
from tests.test_voiceprint_registry import _FakeStore


class _StubOrchestrator:
    def __init__(self, *, result) -> None:
        self._result = result
        self.last_request = None

    async def generate_voiceprint(self, request):
        self.last_request = request
        return self._result

    async def validate_health(self):
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_orchestrator_ready",),
            details={"loaded": True},
        )


class _UnhealthyStubOrchestrator(_StubOrchestrator):
    async def validate_health(self):
        return GenerationOrchestratorHealth(
            state=HealthState.UNAVAILABLE,
            reason_codes=("generation_orchestrator_not_loaded",),
            details={"loaded": False},
        )


class _RaisingStubOrchestrator:
    async def generate_voiceprint(self, request):
        _ = request
        raise RuntimeError("Traceback: model failed at C:/secret/path with key=abc123")

    async def validate_health(self):
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_orchestrator_ready",),
            details={"loaded": True},
        )


class _ReadyBackend:
    @property
    def metadata(self) -> ModelProviderMetadata:
        return ModelProviderMetadata(
            provider_name="test_backend",
            provider_version="1",
            supported_models=("ecapa_v1",),
            supported_representation_formats=("encrypted_representation_v1",),
            available=True,
        )

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        _ = request
        return BackendExecutionResult(
            encrypted_payload=b"enc_payload_v1",
            payload_format_version=1,
            encryption_scheme="aes_gcm_v1",
            key_reference="key_ref_v1",
            model_version="v1",
            schema_version=1,
            representation_format="encrypted_representation_v1",
            provider_confidence=0.93,
        )


def _status_history_success() -> tuple[GenerationStatusEvent, ...]:
    return (
        GenerationStatusEvent(status=GenerationStatus.QUEUED, reason_code=None, timestamp="2026-01-01T00:00:00+00:00"),
        GenerationStatusEvent(status=GenerationStatus.VALIDATING, reason_code=None, timestamp="2026-01-01T00:00:01+00:00"),
        GenerationStatusEvent(status=GenerationStatus.QUALITY_SCORING, reason_code=None, timestamp="2026-01-01T00:00:02+00:00"),
        GenerationStatusEvent(status=GenerationStatus.GENERATING, reason_code=None, timestamp="2026-01-01T00:00:03+00:00"),
        GenerationStatusEvent(status=GenerationStatus.PERSISTING, reason_code=None, timestamp="2026-01-01T00:00:04+00:00"),
        GenerationStatusEvent(status=GenerationStatus.VALIDATING_INTEGRITY, reason_code=None, timestamp="2026-01-01T00:00:05+00:00"),
        GenerationStatusEvent(status=GenerationStatus.COMPLETED, reason_code=None, timestamp="2026-01-01T00:00:06+00:00"),
    )


def _success_result() -> GenerationSuccessResult:
    return GenerationSuccessResult(
        success=True,
        generation_id="gen_001",
        status=GenerationStatus.COMPLETED,
        voiceprint_id="vp_001",
        artifact_id="artifact_001",
        revision=1,
        lineage_root_id="vp_001",
        model_name="ecapa_v1",
        model_version="v1",
        schema_version=1,
        validation_summary=ValidationSummary(
            passed=True,
            reason_code="validation_ready",
            sample_count=6,
            findings=(),
        ),
        quality_summary=QualitySummary(
            passed=True,
            reason_code="quality_ready",
            score=0.9,
            threshold=0.75,
            findings=(),
            status="excellent",
            recommendation="generation_recommended",
            threshold_outcome="pass",
        ),
        integrity_summary=IntegrityValidationSummary(
            passed=True,
            reason_codes=("artifact_integrity_ready",),
            finding_count=0,
        ),
        status_history=_status_history_success(),
        requested_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:06+00:00",
        diagnostics={"status_count": 7, "sample_count": 6},
    )


def _failure_result(
    *,
    category: GenerationFailureCategory,
    reason_code: str,
    diagnostics: dict[str, bool | int | float | str | None] | None = None,
) -> GenerationFailureResult:
    return GenerationFailureResult(
        success=False,
        generation_id="gen_001",
        status=GenerationStatus.CANCELLED if category is GenerationFailureCategory.CANCELLED else GenerationStatus.FAILED,
        failure_category=category,
        reason_code=reason_code,
        validation_summary=ValidationSummary(
            passed=False,
            reason_code="validation_failed",
            sample_count=0,
            findings=("sample_reference_missing",),
        ),
        quality_summary=QualitySummary(
            passed=False,
            reason_code="quality_threshold_not_met",
            score=0.2,
            threshold=0.75,
            findings=("quality_threshold_not_met",),
            failure_category="quality_threshold_not_met",
        ),
        integrity_summary=IntegrityValidationSummary(
            passed=False,
            reason_codes=("digest_mismatch",),
            finding_count=1,
        ),
        status_history=(
            GenerationStatusEvent(status=GenerationStatus.QUEUED, reason_code=None, timestamp="2026-01-01T00:00:00+00:00"),
            GenerationStatusEvent(status=GenerationStatus.FAILED, reason_code=reason_code, timestamp="2026-01-01T00:00:01+00:00"),
        ),
        requested_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        diagnostics=diagnostics or {"source": "concierge"},
    )


def _request() -> GenerateVoiceprintRequest:
    return GenerateVoiceprintRequest.create(
        operation_id="op_001",
        subject_id="person_001",
        source="concierge",
        sample_references=("sample_1", "sample_2", "sample_3", "sample_4", "sample_5", "sample_6"),
        enrollment_references=("enroll_1",),
        prepared_enrollment_inputs=("prepared_1",),
        model_preference="ecapa_v1",
        timeout_seconds=3.0,
        correlation_id="corr_1",
        request_id="req_1",
    )


def _config_manager() -> VoiceIdentityConfigurationManager:
    manager = VoiceIdentityConfigurationManager()
    manager.load_from_entry(
        FakeConfigEntry(
            data={
                "generation": {
                    "model_preference": "ecapa_v1",
                    "min_sample_count": 2,
                    "max_sample_count": 12,
                    "quality_threshold": 0.75,
                    "supported_models": ["ecapa_v1"],
                }
            }
        )
    )
    return manager


@pytest.mark.asyncio
async def test_operation_initialization() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    health = await operation.validate_health()
    assert health.state is HealthState.HEALTHY
    assert health.reason_codes == ("generate_voiceprint_ready",)


@pytest.mark.asyncio
async def test_valid_generate_voiceprint_request_projection() -> None:
    orchestrator = _StubOrchestrator(result=_success_result())
    operation = GenerateVoiceprintOperation.create(orchestrator=orchestrator)
    request = _request()

    _ = await operation.execute(request)
    assert orchestrator.last_request is not None
    assert orchestrator.last_request.identifiers.subject_id == "person_001"
    assert len(orchestrator.last_request.sample_references) == 6


@pytest.mark.asyncio
async def test_successful_end_to_end_generation_projection() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    result = await operation.execute(_request())

    assert result.success is True
    assert result.status is GenerateVoiceprintOperationStatus.COMPLETED
    assert result.voiceprint_id == "vp_001"
    assert result.persistence_summary.persisted is True


@pytest.mark.asyncio
async def test_validation_failure_propagation() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.VALIDATION_FAILED,
                reason_code="validation_failed",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.VALIDATION_FAILED
    assert result.subsystem_failure_category == "validation_failed"


@pytest.mark.asyncio
async def test_quality_failure_propagation_with_fidelity() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.QUALITY_CONFIGURATION_INVALID,
                reason_code="quality_configuration_invalid",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.QUALITY_FAILED
    assert result.subsystem_failure_category == "quality_configuration_invalid"


@pytest.mark.asyncio
async def test_model_failure_propagation() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                reason_code="model_execution_failed",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.MODEL_FAILED


@pytest.mark.asyncio
async def test_persistence_failure_propagation() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.PERSISTENCE_FAILED,
                reason_code="generation_persistence_failed",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.PERSISTENCE_FAILED


@pytest.mark.asyncio
async def test_integrity_failure_propagation() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.INTEGRITY_VALIDATION_FAILED,
                reason_code="integrity_validation_failed",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.INTEGRITY_FAILED


@pytest.mark.asyncio
async def test_operation_level_status_tracking() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    request = _request()

    _ = await operation.execute(request)
    snapshot = await operation.get_status(request.operation_id)

    assert snapshot is not None
    assert snapshot.current_status is GenerateVoiceprintOperationStatus.COMPLETED
    assert tuple(event.status for event in snapshot.history) == (
        GenerateVoiceprintOperationStatus.REQUESTED,
        GenerateVoiceprintOperationStatus.RUNNING,
        GenerateVoiceprintOperationStatus.COMPLETED,
    )


@pytest.mark.asyncio
async def test_operation_cancelled_mapping() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.CANCELLED,
                reason_code="cancelled",
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.OPERATION_CANCELLED
    assert result.status is GenerateVoiceprintOperationStatus.CANCELLED


@pytest.mark.asyncio
async def test_safe_diagnostics_generation() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                reason_code="model_execution_failed",
                diagnostics={"path": "C:/secret/path", "token": "abc123", "sample_count": 2},
            )
        )
    )
    result = await operation.execute(_request())

    assert result.success is False
    assert "path" not in result.diagnostics
    assert "token" not in result.diagnostics


@pytest.mark.asyncio
async def test_no_payload_audio_embedding_exception_leakage() -> None:
    operation = GenerateVoiceprintOperation.create(
        orchestrator=_StubOrchestrator(
            result=_failure_result(
                category=GenerationFailureCategory.MODEL_EXECUTION_FAILED,
                reason_code="model_execution_failed",
                diagnostics={"exception": "Traceback: raw embedding at C:/tmp"},
            )
        )
    )
    result = await operation.execute(_request())
    rendered = str(result)

    assert "Traceback" not in rendered
    assert "embedding" not in rendered
    assert "sample_" not in rendered


def test_preservation_of_subsystem_boundaries() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    assert hasattr(operation, "execute")
    assert not hasattr(operation, "persist_artifact")
    assert not hasattr(operation, "validate_voiceprint")
    assert not hasattr(operation, "register_record")


@pytest.mark.asyncio
async def test_operation_invalid_request_mapping() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    request = GenerateVoiceprintRequest.create(
        operation_id="op_001",
        subject_id="person_001",
        source="concierge",
        sample_references=("sample_1",),
        generation_id="bad generation id",
    )

    result = await operation.execute(request)
    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.OPERATION_INVALID


@pytest.mark.asyncio
async def test_not_loaded_mapping() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    operation.clear()
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.OPERATION_FAILED
    assert result.reason_code == "generate_voiceprint_not_loaded"
    assert tuple(event.status for event in result.operation_status_history) == (
        GenerateVoiceprintOperationStatus.REQUESTED,
        GenerateVoiceprintOperationStatus.FAILED,
    )
    assert result.diagnostics == {"loaded": False}


@pytest.mark.asyncio
async def test_orchestrator_exception_maps_to_operation_internal_error() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_RaisingStubOrchestrator())
    result = await operation.execute(_request())

    assert result.success is False
    assert result.failure_category is GenerateVoiceprintFailureCategory.OPERATION_INTERNAL_ERROR
    assert result.reason_code == "operation_internal_error"
    assert result.diagnostics.get("error") == "operation_internal_error"


@pytest.mark.asyncio
async def test_orchestrator_exception_text_not_exposed() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_RaisingStubOrchestrator())
    result = await operation.execute(_request())
    rendered = str(result)

    assert "Traceback" not in rendered
    assert "secret" not in rendered
    assert "key=abc123" not in rendered


@pytest.mark.asyncio
async def test_operation_status_history_valid_for_failure_paths() -> None:
    not_loaded_operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    not_loaded_operation.clear()
    not_loaded_result = await not_loaded_operation.execute(_request())

    invalid_request_operation = GenerateVoiceprintOperation.create(orchestrator=_StubOrchestrator(result=_success_result()))
    invalid_request = GenerateVoiceprintRequest.create(
        operation_id="op_invalid_001",
        subject_id="person_001",
        source="concierge",
        sample_references=("sample_1",),
        generation_id="bad generation id",
    )
    invalid_request_result = await invalid_request_operation.execute(invalid_request)

    exception_operation = GenerateVoiceprintOperation.create(orchestrator=_RaisingStubOrchestrator())
    exception_result = await exception_operation.execute(_request())

    assert tuple(event.status for event in not_loaded_result.operation_status_history) == (
        GenerateVoiceprintOperationStatus.REQUESTED,
        GenerateVoiceprintOperationStatus.FAILED,
    )
    assert tuple(event.status for event in invalid_request_result.operation_status_history) == (
        GenerateVoiceprintOperationStatus.REQUESTED,
        GenerateVoiceprintOperationStatus.RUNNING,
        GenerateVoiceprintOperationStatus.FAILED,
    )
    assert tuple(event.status for event in exception_result.operation_status_history) == (
        GenerateVoiceprintOperationStatus.REQUESTED,
        GenerateVoiceprintOperationStatus.RUNNING,
        GenerateVoiceprintOperationStatus.FAILED,
    )


@pytest.mark.asyncio
async def test_health_unavailable_when_orchestrator_unhealthy() -> None:
    operation = GenerateVoiceprintOperation.create(orchestrator=_UnhealthyStubOrchestrator(result=_success_result()))
    health = await operation.validate_health()

    assert health.state is HealthState.UNAVAILABLE
    assert health.reason_codes == ("operation_failed",)


@pytest.mark.asyncio
async def test_complete_pipeline_integration_vi110_through_vi109() -> None:
    manager = _config_manager()
    validation = SampleValidationPipelineProvider.create(config_manager=manager)
    quality = QualityScoringEngineProvider.create(config_manager=manager)
    model = ModelExecutionProviderRuntime.create(config_manager=manager, backend=_ReadyBackend())

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
        model_provider=model,
        persistence_engine=persistence,
        integrity_validator=integrity,
    )
    operation = GenerateVoiceprintOperation.create(orchestrator=orchestrator)

    result = await operation.execute(
        GenerateVoiceprintRequest.create(
            operation_id="op_real_001",
            subject_id="person_001",
            source="concierge",
            sample_references=("sample_1", "sample_2", "sample_3"),
            enrollment_references=("enroll_1",),
            prepared_enrollment_inputs=("prepared_1",),
            model_preference="ecapa_v1",
            timeout_seconds=3.0,
        )
    )

    assert result.success is True
    assert result.persistence_summary.persisted is True
    assert result.integrity_summary.passed is True
