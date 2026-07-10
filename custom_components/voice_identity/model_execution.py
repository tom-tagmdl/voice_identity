"""Model execution provider for voiceprint representation generation.

This module owns model execution only. It consumes validated/quality-approved
inputs, produces provider-neutral execution contracts, and returns
VI-110-compatible model artifacts for downstream persistence.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from re import compile as re_compile
from typing import Protocol

from .configuration import VoiceIdentityConfigurationError, VoiceIdentityConfigurationManager
from .generation_orchestrator import (
    GenerationOrchestratorHealth,
    GenerationRequest,
    ModelArtifactPayload,
    ModelExecutionProvider,
    ModelExecutionResult,
    QualityEvaluationResult,
    SampleValidationResult,
)
from .health_state import HealthState

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class ModelExecutionFailureCategory(StrEnum):
    """Safe failure taxonomy for model execution workflows."""

    MODEL_PROVIDER_NOT_LOADED = "model_provider_not_loaded"
    MODEL_PROVIDER_UNAVAILABLE = "model_provider_unavailable"
    MODEL_NOT_CONFIGURED = "model_not_configured"
    UNSUPPORTED_MODEL = "unsupported_model"
    MODEL_INPUT_INVALID = "model_input_invalid"
    MODEL_EXECUTION_FAILED = "model_execution_failed"
    MODEL_OUTPUT_INVALID = "model_output_invalid"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_INTERNAL_ERROR = "model_internal_error"


@dataclass(slots=True, frozen=True)
class ModelProviderMetadata:
    """Safe model provider metadata for capability and diagnostics projection."""

    provider_name: str
    provider_version: str
    supported_models: tuple[str, ...]
    supported_representation_formats: tuple[str, ...]
    available: bool


@dataclass(slots=True, frozen=True)
class BackendExecutionRequest:
    """Provider-neutral backend execution request contract."""

    generation_id: str
    model_id: str
    sample_count: int
    prepared_input_count: int


@dataclass(slots=True, frozen=True)
class BackendExecutionResult:
    """Provider-neutral backend execution result contract."""

    encrypted_payload: bytes
    payload_format_version: int
    encryption_scheme: str
    key_reference: str | None
    model_version: str
    schema_version: int
    representation_format: str
    provider_confidence: float | None = None


class ModelBackendExecutionError(Exception):
    """Safe backend execution failure with machine-readable reason code."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ModelExecutionBackend(Protocol):
    """Backend abstraction for future model execution implementations."""

    @property
    def metadata(self) -> ModelProviderMetadata:
        """Return static backend metadata."""

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        """Execute one backend model generation request."""


class UnavailableModelExecutionBackend:
    """Fail-closed production backend placeholder until approved model runtime exists."""

    @property
    def metadata(self) -> ModelProviderMetadata:
        return ModelProviderMetadata(
            provider_name="unavailable_backend",
            provider_version="0",
            supported_models=(),
            supported_representation_formats=("encrypted_representation_v1",),
            available=False,
        )

    async def execute(self, request: BackendExecutionRequest) -> BackendExecutionResult:
        _ = request
        raise ModelBackendExecutionError(
            ModelExecutionFailureCategory.MODEL_PROVIDER_UNAVAILABLE.value,
        )


class ModelExecutionProviderRuntime(ModelExecutionProvider):
    """Runtime model execution provider implementation for VI-113."""

    def __init__(
        self,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        backend: ModelExecutionBackend,
    ) -> None:
        self._config_manager = config_manager
        self._backend = backend
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        backend: ModelExecutionBackend | None = None,
    ) -> ModelExecutionProviderRuntime:
        return cls(
            config_manager=config_manager,
            backend=backend or UnavailableModelExecutionBackend(),
        )

    async def generate(
        self,
        *,
        request: GenerationRequest,
        validation: SampleValidationResult,
        quality: QualityEvaluationResult,
    ) -> ModelExecutionResult:
        if not self._loaded:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_PROVIDER_NOT_LOADED.value,
                diagnostics={"loaded": False},
            )

        try:
            config = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_NOT_CONFIGURED.value,
                diagnostics={"loaded": True},
            )

        selected_model = _safe_token(
            request.options.model_preference or config.generation.model_preference,
            config.generation.model_preference,
        )
        supported_models = tuple(config.generation.supported_models)
        backend_meta = self._backend.metadata
        safe_provider_name = _safe_metadata_token(backend_meta.provider_name, "unknown_provider")
        safe_provider_version = _safe_metadata_token(backend_meta.provider_version, "unknown_version")

        if not supported_models:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_NOT_CONFIGURED.value,
                diagnostics={"loaded": True, "supported_model_count": 0},
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        if selected_model not in supported_models:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.UNSUPPORTED_MODEL.value,
                diagnostics={
                    "loaded": True,
                    "supported_model_count": len(supported_models),
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        if not backend_meta.available:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_PROVIDER_UNAVAILABLE.value,
                diagnostics={"loaded": True, "provider_available": False},
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        if not validation.passed or not quality.passed:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_INPUT_INVALID.value,
                diagnostics={
                    "loaded": True,
                    "validation_passed": validation.passed,
                    "quality_passed": quality.passed,
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        if not request.sample_references:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_INPUT_INVALID.value,
                diagnostics={"loaded": True, "sample_count": 0},
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        backend_request = BackendExecutionRequest(
            generation_id=request.identifiers.generation_id,
            model_id=selected_model,
            sample_count=len(request.sample_references),
            prepared_input_count=len(request.prepared_enrollment_inputs),
        )

        timeout = request.options.timeout_seconds
        started = time.monotonic()
        try:
            if timeout is not None and timeout > 0:
                backend_result = await asyncio.wait_for(
                    self._backend.execute(backend_request),
                    timeout=timeout,
                )
            else:
                backend_result = await self._backend.execute(backend_request)
        except asyncio.TimeoutError:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_TIMEOUT.value,
                diagnostics={
                    "loaded": True,
                    "timeout_configured": bool(timeout),
                    "sample_count": len(request.sample_references),
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )
        except ModelBackendExecutionError as err:
            safe_reason = _safe_token(
                err.reason_code,
                ModelExecutionFailureCategory.MODEL_EXECUTION_FAILED.value,
            )
            return _failure_result(
                reason_code=safe_reason,
                diagnostics={
                    "loaded": True,
                    "sample_count": len(request.sample_references),
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )
        except Exception:
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_INTERNAL_ERROR.value,
                diagnostics={
                    "loaded": True,
                    "sample_count": len(request.sample_references),
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        if not _is_valid_backend_result(backend_result):
            return _failure_result(
                reason_code=ModelExecutionFailureCategory.MODEL_OUTPUT_INVALID.value,
                diagnostics={
                    "loaded": True,
                    "sample_count": len(request.sample_references),
                },
                provider_name=safe_provider_name,
                provider_version=safe_provider_version,
                provider_available=backend_meta.available,
            )

        suffix = request.identifiers.generation_id[-12:]
        artifact = ModelArtifactPayload(
            voiceprint_id=f"vp_{suffix}",
            artifact_id=f"artifact_{suffix}",
            encrypted_payload=backend_result.encrypted_payload,
            payload_format_version=backend_result.payload_format_version,
            encryption_scheme=backend_result.encryption_scheme,
            key_reference=backend_result.key_reference,
            model_name=selected_model,
            model_version=backend_result.model_version,
            schema_version=backend_result.schema_version,
        )

        duration_ms = int((time.monotonic() - started) * 1000)
        confidence = _safe_confidence(backend_result.provider_confidence)
        diagnostics: dict[str, bool | int | float | str | None] = {
            "loaded": True,
            "provider": safe_provider_name,
            "provider_version": safe_provider_version,
            "sample_count": len(request.sample_references),
            "prepared_input_count": len(request.prepared_enrollment_inputs),
            "execution_duration_ms": duration_ms,
            "representation_format": backend_result.representation_format,
            "provider_available": backend_meta.available,
        }
        if confidence is not None:
            diagnostics["provider_confidence"] = confidence

        return ModelExecutionResult(
            success=True,
            reason_code="model_execution_ready",
            artifact=artifact,
            diagnostics=diagnostics,
        )

    async def validate_health(self) -> GenerationOrchestratorHealth:
        if not self._loaded:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(ModelExecutionFailureCategory.MODEL_PROVIDER_NOT_LOADED.value,),
                details={"loaded": False},
            )

        try:
            config = self._config_manager.config
        except VoiceIdentityConfigurationError:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(ModelExecutionFailureCategory.MODEL_NOT_CONFIGURED.value,),
                details={"loaded": True},
            )

        backend_meta = self._backend.metadata
        if not backend_meta.available:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(ModelExecutionFailureCategory.MODEL_PROVIDER_UNAVAILABLE.value,),
                details={
                    "loaded": True,
                    "provider": _safe_metadata_token(backend_meta.provider_name, "unknown_provider"),
                    "provider_version": _safe_metadata_token(backend_meta.provider_version, "unknown_version"),
                    "provider_available": False,
                },
            )

        selected = _safe_token(config.generation.model_preference, config.generation.model_preference)
        if selected not in config.generation.supported_models:
            return GenerationOrchestratorHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(ModelExecutionFailureCategory.UNSUPPORTED_MODEL.value,),
                details={
                    "loaded": True,
                    "provider": _safe_metadata_token(backend_meta.provider_name, "unknown_provider"),
                    "provider_version": _safe_metadata_token(backend_meta.provider_version, "unknown_version"),
                    "provider_available": True,
                },
            )

        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("model_execution_ready",),
            details={
                "loaded": True,
                "provider": _safe_metadata_token(backend_meta.provider_name, "unknown_provider"),
                "provider_version": _safe_metadata_token(backend_meta.provider_version, "unknown_version"),
                "provider_available": True,
                "supported_model_count": len(config.generation.supported_models),
            },
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


def _failure_result(
    *,
    reason_code: str,
    diagnostics: dict[str, bool | int | float | str | None],
    provider_name: str | None = None,
    provider_version: str | None = None,
    provider_available: bool | None = None,
) -> ModelExecutionResult:
    safe_reason = _safe_token(reason_code, ModelExecutionFailureCategory.MODEL_EXECUTION_FAILED.value)
    safe_diagnostics: dict[str, bool | int | float | str | None] = dict(diagnostics)
    if provider_name is not None:
        safe_diagnostics["provider"] = _safe_metadata_token(provider_name, "unknown_provider")
    if provider_version is not None:
        safe_diagnostics["provider_version"] = _safe_metadata_token(provider_version, "unknown_version")
    if provider_available is not None:
        safe_diagnostics["provider_available"] = provider_available

    return ModelExecutionResult(
        success=False,
        reason_code=safe_reason,
        artifact=None,
        diagnostics=safe_diagnostics,
    )


def _is_valid_backend_result(result: BackendExecutionResult) -> bool:
    if not result.encrypted_payload:
        return False
    if result.payload_format_version < 1:
        return False
    if result.schema_version < 1:
        return False
    if not _SAFE_TOKEN_PATTERN.fullmatch(result.encryption_scheme):
        return False
    if not _SAFE_TOKEN_PATTERN.fullmatch(result.model_version):
        return False
    if not _SAFE_TOKEN_PATTERN.fullmatch(result.representation_format):
        return False
    if result.key_reference is not None and not _SAFE_TOKEN_PATTERN.fullmatch(result.key_reference):
        return False
    return True


def _safe_token(value: str | None, fallback: str) -> str:
    if value is not None:
        normalized = value.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
            return normalized

    normalized_fallback = fallback.strip().lower()
    if _SAFE_TOKEN_PATTERN.fullmatch(normalized_fallback):
        return normalized_fallback
    return ModelExecutionFailureCategory.MODEL_EXECUTION_FAILED.value


def _safe_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    return min(1.0, max(0.0, float(value)))


def _safe_metadata_token(value: str | None, fallback: str) -> str:
    return _safe_token(value, fallback)