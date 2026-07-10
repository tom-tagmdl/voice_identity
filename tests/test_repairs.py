from __future__ import annotations

from dataclasses import asdict

import pytest

from custom_components.voice_identity.repair_definitions import RepairDefinition, RepairSeverity
from custom_components.voice_identity.repair_registry import (
    VoiceIdentityRepairDefinitionDuplicateError,
    VoiceIdentityRepairRegistry,
)
from custom_components.voice_identity.repair_resolver import (
    RepairResolutionStatus,
    VoiceIdentityRepairResolver,
)


def test_repair_registry_registers_and_resolves_by_reason_code() -> None:
    registry = VoiceIdentityRepairRegistry.with_defaults()

    definitions = registry.resolve_by_reason_code("voiceprint_artifact_missing")

    assert definitions
    assert all(isinstance(item, RepairDefinition) for item in definitions)
    assert "repair_artifact_missing_reenroll" in {item.repair_id for item in definitions}


def test_repair_registry_lookup_is_deterministic_for_same_reason_set() -> None:
    registry = VoiceIdentityRepairRegistry.with_defaults()

    first = registry.resolve_by_reason_codes(
        ("operation_failed", "voiceprint_artifact_missing", "model_provider_unavailable")
    )
    second = registry.resolve_by_reason_codes(
        ("voiceprint_artifact_missing", "model_provider_unavailable", "operation_failed")
    )

    assert first == second


def test_repair_registry_rejects_duplicate_registration() -> None:
    registry = VoiceIdentityRepairRegistry.with_defaults()
    duplicate = registry.snapshot().definitions[0]

    with pytest.raises(VoiceIdentityRepairDefinitionDuplicateError):
        registry.register(duplicate)


def test_repair_registry_returns_empty_for_unknown_reason() -> None:
    registry = VoiceIdentityRepairRegistry.with_defaults()

    result = registry.resolve_by_reason_code("new_unknown_reason_code")

    assert result == ()


def test_repair_resolver_returns_repair_available_for_known_failure() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    result = resolver.resolve(
        {
            "reason_code": "voiceprint_artifact_missing",
            "repair_hint_code": "run_registry_reconciliation",
            "suggested_next_action_code": "regenerate_enrollment",
            "is_retryable": False,
            "is_repairable_candidate": True,
            "issue_reason_codes": ["voiceprint_artifact_missing"],
        }
    )

    assert result.status is RepairResolutionStatus.REPAIR_AVAILABLE
    assert result.repairable is True
    assert result.retryable is False
    assert result.repairs
    assert result.repairs[0].severity in {RepairSeverity.HIGH.value, RepairSeverity.CRITICAL.value}


def test_repair_resolver_is_deterministic_for_identical_input() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())
    failure = {
        "reason_code": "operation_failed",
        "repair_hint_code": "check_generation_pipeline",
        "suggested_next_action_code": "retry_generation_operation",
        "is_retryable": True,
        "is_repairable_candidate": True,
        "issue_reason_codes": ["operation_failed", "model_provider_unavailable"],
    }

    first = resolver.resolve(failure)
    second = resolver.resolve(failure)

    assert first == second


def test_repair_resolver_returns_retry_recommended_when_retryable_without_mapping() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    result = resolver.resolve(
        {
            "reason_code": "runtime_retryable_transient",
            "repair_hint_code": "review_component_health",
            "suggested_next_action_code": "retry_operation",
            "is_retryable": True,
            "is_repairable_candidate": False,
            "issue_reason_codes": ["runtime_retryable_transient"],
        }
    )

    assert result.status is RepairResolutionStatus.RETRY_RECOMMENDED
    assert result.repairs == ()


def test_repair_resolver_returns_manual_intervention_when_no_mapping_but_candidate() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    result = resolver.resolve(
        {
            "reason_code": "future_supported_failure",
            "repair_hint_code": "review_component_health",
            "suggested_next_action_code": "manual_review",
            "is_retryable": False,
            "is_repairable_candidate": True,
            "issue_reason_codes": ["future_supported_failure"],
        }
    )

    assert result.status is RepairResolutionStatus.MANUAL_INTERVENTION_REQUIRED
    assert result.repairs == ()


def test_repair_resolver_returns_diagnostics_unavailable_when_failure_missing() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    result = resolver.resolve(None)

    assert result.status is RepairResolutionStatus.DIAGNOSTICS_UNAVAILABLE
    assert result.reason_code == "diagnostics_unavailable"


def test_repair_recommendation_projection_is_serializable_and_safe() -> None:
    resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

    result = resolver.resolve(
        {
            "reason_code": "voiceprint_artifact_missing",
            "repair_hint_code": "run_registry_reconciliation",
            "suggested_next_action_code": "regenerate_enrollment",
            "is_retryable": False,
            "is_repairable_candidate": True,
            "issue_reason_codes": ["voiceprint_artifact_missing"],
        }
    )

    payload = result.to_dict()

    assert payload["status"] == "repair_available"
    assert isinstance(payload["repairs"], list)
    assert payload["repairs"]
    assert all("/" not in item["operator_guidance"] for item in payload["repairs"])
    assert all("path" not in item["operator_guidance"].lower() for item in payload["repairs"])


def test_repair_registry_snapshot_is_sorted_and_serializable() -> None:
    registry = VoiceIdentityRepairRegistry.with_defaults()

    snapshot = registry.snapshot()
    serialized = [asdict(definition) for definition in snapshot.definitions]

    assert serialized == sorted(serialized, key=lambda item: item["repair_id"])
