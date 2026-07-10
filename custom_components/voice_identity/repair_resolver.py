"""Repair resolution for diagnostics-driven recommendation projection.

This module translates normalized diagnostics metadata into deterministic,
operator-safe repair recommendations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from re import compile as re_compile

from .diagnostics_sanitizer import normalize_reason_code, safe_token
from .repair_registry import VoiceIdentityRepairRegistry


class RepairResolutionStatus(StrEnum):
    """Outcome taxonomy for repair recommendation resolution."""

    REPAIR_AVAILABLE = "repair_available"
    REPAIR_NOT_AVAILABLE = "repair_not_available"
    RETRY_RECOMMENDED = "retry_recommended"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"
    UNSUPPORTED_FAILURE_TYPE = "unsupported_failure_type"
    DIAGNOSTICS_UNAVAILABLE = "diagnostics_unavailable"


@dataclass(slots=True, frozen=True)
class RepairRecommendation:
    """Serializable recommendation payload built from registry definitions."""

    repair_id: str
    title: str
    description: str
    severity: str
    repair_category: str
    operator_guidance: str
    validation_guidance: str
    retryable: bool
    repairable: bool
    supported_reason_codes: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RepairResolutionResult:
    """Deterministic service payload for operator-safe repair recommendations."""

    status: RepairResolutionStatus
    repairable: bool
    retryable: bool
    reason_code: str
    repair_hint_code: str
    suggested_next_action_code: str
    repairs: tuple[RepairRecommendation, ...]

    def to_dict(self) -> dict[str, object]:
        """Return sanitized dictionary projection for service responses."""
        repairs_payload: list[dict[str, object]] = []
        for item in self.repairs:
            serialized = asdict(item)
            serialized["title"] = _sanitize_guidance_text(str(serialized.get("title", "")))
            serialized["description"] = _sanitize_guidance_text(str(serialized.get("description", "")))
            serialized["operator_guidance"] = _sanitize_guidance_text(
                str(serialized.get("operator_guidance", ""))
            )
            serialized["validation_guidance"] = _sanitize_guidance_text(
                str(serialized.get("validation_guidance", ""))
            )
            repairs_payload.append(serialized)

        return {
            "status": self.status.value,
            "repairable": self.repairable,
            "retryable": self.retryable,
            "reason_code": self.reason_code,
            "repair_hint_code": self.repair_hint_code,
            "suggested_next_action_code": self.suggested_next_action_code,
            "repairs": repairs_payload,
        }


class VoiceIdentityRepairResolver:
    """Resolve diagnostics failure payloads into deterministic repair guidance."""

    def __init__(self, *, registry: VoiceIdentityRepairRegistry) -> None:
        self._registry = registry

    def resolve(self, failure_summary: Mapping[str, object] | None) -> RepairResolutionResult:
        """Resolve recommendations from diagnostics failure summary data."""
        if not isinstance(failure_summary, Mapping):
            return self._diagnostics_unavailable_result()

        raw_reason_code = failure_summary.get("reason_code", None)
        reason_code = normalize_reason_code(str(raw_reason_code)) if raw_reason_code is not None else "no_issues"

        repair_hint_code = safe_token(
            str(failure_summary.get("repair_hint_code", "") or ""),
            "review_component_health",
        )
        suggested_next_action_code = safe_token(
            str(failure_summary.get("suggested_next_action_code", "") or ""),
            "review_component_health",
        )

        retryable = bool(failure_summary.get("is_retryable", False))
        repairable_candidate = bool(failure_summary.get("is_repairable_candidate", False))

        reason_codes = _as_reason_code_tuple(failure_summary.get("issue_reason_codes"))
        if not reason_codes and reason_code not in {"no_issues", "unknown_reason"}:
            reason_codes = (reason_code,)

        if reason_codes and reason_code == "no_issues":
            reason_code = reason_codes[0]

        if "diagnostics_unavailable" in reason_codes:
            return self._diagnostics_unavailable_result()

        recommendations = self._registry.resolve_by_reason_codes(reason_codes)
        projected = tuple(
            RepairRecommendation(
                repair_id=definition.repair_id,
                title=definition.title,
                description=definition.description,
                severity=definition.severity.value,
                repair_category=definition.repair_category.value,
                operator_guidance=definition.operator_guidance,
                validation_guidance=definition.validation_guidance,
                retryable=definition.retryable,
                repairable=definition.repairable,
                supported_reason_codes=definition.supported_reason_codes,
            )
            for definition in recommendations
        )

        if projected:
            return RepairResolutionResult(
                status=RepairResolutionStatus.REPAIR_AVAILABLE,
                repairable=any(item.repairable for item in projected),
                retryable=retryable or any(item.retryable for item in projected),
                reason_code=reason_code,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                repairs=projected,
            )

        if retryable:
            return RepairResolutionResult(
                status=RepairResolutionStatus.RETRY_RECOMMENDED,
                repairable=repairable_candidate,
                retryable=True,
                reason_code=reason_code,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                repairs=(),
            )

        if reason_code == "unknown_reason":
            status = RepairResolutionStatus.UNSUPPORTED_FAILURE_TYPE
        elif repairable_candidate:
            status = RepairResolutionStatus.MANUAL_INTERVENTION_REQUIRED
        else:
            status = RepairResolutionStatus.REPAIR_NOT_AVAILABLE

        return RepairResolutionResult(
            status=status,
            repairable=repairable_candidate,
            retryable=False,
            reason_code=reason_code,
            repair_hint_code=repair_hint_code,
            suggested_next_action_code=suggested_next_action_code,
            repairs=(),
        )

    def _diagnostics_unavailable_result(self) -> RepairResolutionResult:
        return RepairResolutionResult(
            status=RepairResolutionStatus.DIAGNOSTICS_UNAVAILABLE,
            repairable=False,
            retryable=False,
            reason_code="diagnostics_unavailable",
            repair_hint_code="review_component_health",
            suggested_next_action_code="reload_voice_identity",
            repairs=(),
        )


def _as_reason_code_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()

    normalized = {
        normalize_reason_code(str(item))
        for item in value
    }
    return tuple(sorted(normalized))


_UNSAFE_GUIDANCE_PATTERN = re_compile(
    r"traceback|exception|stack|secret|token|password|apikey|api_key|[a-z]:\\|/",
    flags=0,
)


def _sanitize_guidance_text(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    lowered = candidate.lower()
    if _UNSAFE_GUIDANCE_PATTERN.search(lowered) is not None:
        return "redacted"
    return candidate
