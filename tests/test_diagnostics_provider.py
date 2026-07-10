from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from custom_components.voice_identity.const import (
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_GENERATE_VOICEPRINT_OPERATION,
    DATA_GENERATION_ORCHESTRATOR,
    DATA_GET_CAPABILITIES_OPERATION,
    DATA_GET_VOICEPRINT_STATUS_OPERATION,
    DATA_HEALTH_ENGINE,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DATA_VOICEPRINT_REVISION_MANAGER,
)
from custom_components.voice_identity.diagnostics_provider import (
    VoiceIdentityDiagnosticsProvider,
    build_runtime_context,
)
from custom_components.voice_identity.diagnostics_sanitizer import normalize_reason_code, sanitize_mapping
from custom_components.voice_identity.health_state import ComponentHealthReport, HealthSnapshot, HealthState


class _StubHealthEngine:
    def __init__(self, snapshot: HealthSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> HealthSnapshot:
        return self._snapshot


class _StubCapabilityRegistry:
    def snapshot(self):
        diagnostics_descriptor = SimpleNamespace(name="diagnostics")
        return SimpleNamespace(
            registry_schema_version=1,
            config_schema_version=1,
            capabilities=(
                SimpleNamespace(descriptor=diagnostics_descriptor, enabled=True),
                SimpleNamespace(descriptor=SimpleNamespace(name="voiceprint_storage"), enabled=True),
            ),
        )


def _contains_key(payload: object, forbidden_key: str) -> bool:
    if isinstance(payload, Mapping):
        if forbidden_key in payload:
            return True
        return any(_contains_key(value, forbidden_key) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_key(value, forbidden_key) for value in payload)
    return False


def _runtime_payload() -> dict[str, object]:
    health = HealthSnapshot(
        state=HealthState.DEGRADED,
        reason_codes=("Model Timeout", "storage_permission_denied"),
        components=(
            ComponentHealthReport(
                component="model_execution_provider",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=("Model Timeout", "model_provider_unavailable"),
                details={
                    "provider": "backend_v1",
                    "provider_available": False,
                    "exception": "Traceback: secret key=abc123",
                    "payload_path": "C:/secrets/raw.bin",
                },
            ),
            ComponentHealthReport(
                component="voiceprint_registry",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_artifact_missing",),
                details={
                    "loaded": True,
                    "record_count": 2,
                    "audio_blob": "should_not_emit",
                },
            ),
            ComponentHealthReport(
                component="generation_orchestrator",
                required=True,
                state=HealthState.DEGRADED,
                reason_codes=("operation_internal_error",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="generate_voiceprint_operation",
                required=True,
                state=HealthState.DEGRADED,
                reason_codes=("operation_failed",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="get_voiceprint_status_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("get_voiceprint_status_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="get_capabilities_operation",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("get_capabilities_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="voiceprint_lifecycle_manager",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_lifecycle_ready",),
                details={"loaded": True},
            ),
            ComponentHealthReport(
                component="voiceprint_revision_manager",
                required=True,
                state=HealthState.HEALTHY,
                reason_codes=("voiceprint_revision_ready",),
                details={"loaded": True},
            ),
        ),
    )

    config = SimpleNamespace(
        config_schema_version=1,
        service=SimpleNamespace(enabled=True),
        diagnostics=SimpleNamespace(enabled=True),
        generation=SimpleNamespace(
            model_preference="ecapa_v1",
            supported_models=("ecapa_v1",),
            min_sample_count=8,
            max_sample_count=12,
            quality_threshold=0.75,
        ),
    )

    return {
        DATA_CONFIG_MANAGER: SimpleNamespace(config=config),
        DATA_HEALTH_ENGINE: _StubHealthEngine(health),
        DATA_CAPABILITY_REGISTRY: _StubCapabilityRegistry(),
        DATA_MODEL_EXECUTION_PROVIDER: object(),
        DATA_VOICEPRINT_REGISTRY: object(),
        DATA_VOICEPRINT_LIFECYCLE_MANAGER: object(),
        DATA_VOICEPRINT_REVISION_MANAGER: object(),
        DATA_GENERATION_ORCHESTRATOR: object(),
        DATA_GENERATE_VOICEPRINT_OPERATION: object(),
        DATA_GET_VOICEPRINT_STATUS_OPERATION: object(),
        DATA_GET_CAPABILITIES_OPERATION: object(),
    }


@pytest.mark.asyncio
async def test_diagnostics_provider_returns_expected_sections() -> None:
    provider = VoiceIdentityDiagnosticsProvider()
    runtime = _runtime_payload()

    result = await provider.collect(
        context=build_runtime_context(entry_id="entry_1", runtime=runtime),
        source="service_get_diagnostics",
    )

    assert set(result) == {
        "entry_id",
        "source",
        "platform",
        "model",
        "enrollment",
        "generation",
        "registry",
        "capability",
        "failure",
    }
    assert result["platform"]["health_state"] == "degraded"
    assert result["model"]["state"] == "unavailable"
    assert result["registry"]["record_count"] == 2


@pytest.mark.asyncio
async def test_diagnostics_provider_normalizes_reasons_and_maps_hints() -> None:
    provider = VoiceIdentityDiagnosticsProvider()

    result = await provider.collect(
        context=build_runtime_context(entry_id="entry_1", runtime=_runtime_payload()),
        source="service_get_diagnostics",
    )

    reason_codes = result["failure"]["issue_reason_codes"]
    assert "unknown_reason" in reason_codes
    assert "model_provider_unavailable" in reason_codes
    assert "voiceprint_artifact_missing" in reason_codes
    assert "verify_model_backend" in result["failure"]["repair_hint_codes"]
    assert "run_registry_reconciliation" in result["failure"]["repair_hint_codes"]
    assert result["failure"]["reason_code"] in reason_codes
    assert result["failure"]["repair_hint_code"] in result["failure"]["repair_hint_codes"]
    assert result["failure"]["suggested_next_action_code"] in result["failure"]["suggested_next_action_codes"]
    assert isinstance(result["failure"]["is_retryable"], bool)
    assert isinstance(result["failure"]["is_repairable_candidate"], bool)


@pytest.mark.asyncio
async def test_diagnostics_provider_strips_prohibited_fields_and_text_leaks() -> None:
    provider = VoiceIdentityDiagnosticsProvider()

    result = await provider.collect(
        context=build_runtime_context(entry_id="entry_1", runtime=_runtime_payload()),
        source="service_get_diagnostics",
    )

    for forbidden in {
        "audio",
        "audio_blob",
        "embedding",
        "vector",
        "transcript",
        "payload",
        "path",
        "token",
        "secret",
        "exception",
        "stack",
    }:
        assert _contains_key(result, forbidden) is False


@pytest.mark.asyncio
async def test_diagnostics_provider_output_is_deterministic() -> None:
    provider = VoiceIdentityDiagnosticsProvider()
    runtime = _runtime_payload()

    first = await provider.collect(
        context=build_runtime_context(entry_id="entry_1", runtime=runtime),
        source="service_get_diagnostics",
    )
    second = await provider.collect(
        context=build_runtime_context(entry_id="entry_1", runtime=runtime),
        source="service_get_diagnostics",
    )

    assert first == second


def test_sanitizer_normalizes_reason_codes_and_nested_mappings() -> None:
    assert normalize_reason_code("MODEL_TIMEOUT") == "model_timeout"
    assert normalize_reason_code("model_timeout") == "model_timeout"

    payload = sanitize_mapping(
        {
            "safe_key": "model_timeout",
            "recording_path": "C:/secret/path",
            "nested": {
                "token": "abc123",
                "status": "healthy",
                "trace": "Traceback: hidden",
            },
        }
    )

    assert "recording_path" not in payload
    assert "token" not in payload["nested"]
    assert payload["nested"]["status"] == "healthy"
