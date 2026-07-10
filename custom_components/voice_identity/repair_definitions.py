"""Canonical repair definitions for Voice Identity diagnostics failures.

Repairs in this module are recommendation-only metadata.
They do not execute remediation actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RepairSeverity(StrEnum):
    """Severity used for operator-facing recommendation prioritization."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RepairCategory(StrEnum):
    """Classification bucket for repair recommendations."""

    ARTIFACT = "artifact"
    REGISTRY = "registry"
    ENROLLMENT = "enrollment"
    MODEL = "model"
    CAPABILITY = "capability"
    OPERATIONS = "operations"


@dataclass(slots=True, frozen=True)
class RepairDefinition:
    """Immutable definition for one operator-safe repair recommendation."""

    repair_id: str
    title: str
    description: str
    severity: RepairSeverity
    repair_category: RepairCategory
    supported_reason_codes: tuple[str, ...]
    operator_guidance: str
    validation_guidance: str
    retryable: bool
    repairable: bool


def default_repair_definitions() -> tuple[RepairDefinition, ...]:
    """Return built-in deterministic repair catalog."""
    return (
        RepairDefinition(
            repair_id="repair_artifact_missing_reenroll",
            title="Active voiceprint artifact is missing",
            description=(
                "The active voiceprint reference cannot locate its persisted artifact."
            ),
            severity=RepairSeverity.HIGH,
            repair_category=RepairCategory.ARTIFACT,
            supported_reason_codes=(
                "voiceprint_artifact_missing",
                "artifact_missing",
            ),
            operator_guidance=(
                "Regenerate enrollment for the affected voice profile to create a new active voiceprint."
            ),
            validation_guidance=(
                "Run diagnostics again and confirm artifact and registry checks return healthy without missing-artifact reasons."
            ),
            retryable=False,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_artifact_superseded_refresh_reference",
            title="Voiceprint artifact is superseded",
            description=(
                "The requested voiceprint is no longer active because a newer revision superseded it."
            ),
            severity=RepairSeverity.MEDIUM,
            repair_category=RepairCategory.REGISTRY,
            supported_reason_codes=(
                "voiceprint_artifact_superseded",
                "voiceprint_not_active",
            ),
            operator_guidance=(
                "Use the latest active voiceprint reference and retire stale references in dependent workflows."
            ),
            validation_guidance=(
                "Confirm diagnostics report an active revision and no superseded-reference reasons for the target profile."
            ),
            retryable=False,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_integrity_regenerate_voiceprint",
            title="Voiceprint integrity validation failed",
            description=(
                "Stored voiceprint artifact failed checksum or payload integrity validation."
            ),
            severity=RepairSeverity.CRITICAL,
            repair_category=RepairCategory.ARTIFACT,
            supported_reason_codes=(
                "voiceprint_checksum_failed",
                "digest_mismatch",
                "payload_corrupted",
                "artifact_unreadable",
            ),
            operator_guidance=(
                "Generate a replacement voiceprint from enrollment samples and promote it as the active revision."
            ),
            validation_guidance=(
                "Re-run diagnostics and verify integrity-related reason codes are no longer present."
            ),
            retryable=False,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_metadata_reconcile_registry",
            title="Voiceprint metadata is invalid",
            description=(
                "Registry and artifact metadata are inconsistent or structurally invalid."
            ),
            severity=RepairSeverity.HIGH,
            repair_category=RepairCategory.REGISTRY,
            supported_reason_codes=(
                "voiceprint_metadata_invalid",
                "metadata_invalid",
                "registry_reference_missing",
                "registry_reference_invalid",
                "registry_inconsistent",
                "revision_inconsistent",
            ),
            operator_guidance=(
                "Run the standard voiceprint reconciliation workflow and replace invalid revisions with a clean active revision."
            ),
            validation_guidance=(
                "Verify registry and revision diagnostics return healthy and no metadata consistency reasons remain."
            ),
            retryable=False,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_model_backend_restore",
            title="Model backend is unavailable",
            description=(
                "Voiceprint generation backend is unavailable or not loaded for execution."
            ),
            severity=RepairSeverity.HIGH,
            repair_category=RepairCategory.MODEL,
            supported_reason_codes=(
                "model_backend_unavailable",
                "model_provider_unavailable",
                "model_provider_not_loaded",
            ),
            operator_guidance=(
                "Restore model backend availability and verify model configuration before retrying generation requests."
            ),
            validation_guidance=(
                "Confirm model diagnostics report provider available and no backend-unavailable reason codes."
            ),
            retryable=True,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_enrollment_resume_capture",
            title="Enrollment is incomplete",
            description=(
                "Enrollment did not reach minimum readiness requirements for voiceprint generation."
            ),
            severity=RepairSeverity.MEDIUM,
            repair_category=RepairCategory.ENROLLMENT,
            supported_reason_codes=(
                "enrollment_incomplete",
                "sample_validation_failed",
            ),
            operator_guidance=(
                "Capture additional enrollment samples until readiness gates are satisfied, then regenerate the voiceprint."
            ),
            validation_guidance=(
                "Confirm readiness diagnostics meet enrollment thresholds and generation succeeds without enrollment-incomplete reasons."
            ),
            retryable=True,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_generation_retry_or_review",
            title="Voiceprint generation failed",
            description=(
                "Voiceprint generation pipeline failed and did not produce a valid active revision."
            ),
            severity=RepairSeverity.HIGH,
            repair_category=RepairCategory.OPERATIONS,
            supported_reason_codes=(
                "voiceprint_generation_failed",
                "generation_failed",
                "operation_failed",
                "operation_internal_error",
            ),
            operator_guidance=(
                "Retry generation once prerequisites are healthy, and escalate for manual review if failures continue."
            ),
            validation_guidance=(
                "Confirm generation diagnostics return healthy and no generation-failure reason codes remain."
            ),
            retryable=True,
            repairable=True,
        ),
        RepairDefinition(
            repair_id="repair_capability_unavailable_restore",
            title="Required capability is unavailable",
            description=(
                "A required Voice Identity capability is unavailable for the requested operation."
            ),
            severity=RepairSeverity.MEDIUM,
            repair_category=RepairCategory.CAPABILITY,
            supported_reason_codes=(
                "capability_unavailable",
                "identity_provider_unavailable",
                "operation_not_loaded",
            ),
            operator_guidance=(
                "Restore required capability availability and confirm integration configuration enables the needed operation."
            ),
            validation_guidance=(
                "Check capability diagnostics and confirm required capability status is enabled and healthy."
            ),
            retryable=True,
            repairable=True,
        ),
    )
