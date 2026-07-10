"""Diagnostics provider for Voice Identity integration.

This module exposes a deterministic, read-only diagnostics projection that is
safe for Home Assistant diagnostics and service consumers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_GENERATE_VOICEPRINT_OPERATION,
    DATA_GENERATION_ORCHESTRATOR,
    DATA_GET_CAPABILITIES_OPERATION,
    DATA_GET_VOICEPRINT_STATUS_OPERATION,
    DATA_HEALTH_ENGINE,
    DATA_HEALTH_TELEMETRY_PROVIDER,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DATA_VOICEPRINT_REVISION_MANAGER,
)
from .diagnostics_sanitizer import normalize_reason_code, safe_token, sanitize_mapping

_REPAIR_HINTS: dict[str, str] = {
    "configuration_invalid": "verify_configuration",
    "configuration_migration_required": "run_configuration_migration",
    "storage_unavailable": "verify_storage_provider",
    "storage_permission_denied": "verify_storage_permissions",
    "voiceprint_registry_not_loaded": "reload_voice_identity",
    "voiceprint_artifact_missing": "run_registry_reconciliation",
    "model_not_configured": "verify_model_configuration",
    "model_provider_unavailable": "verify_model_backend",
    "model_provider_not_loaded": "reload_voice_identity",
    "generation_orchestrator_not_loaded": "reload_generation_orchestrator",
    "operation_not_loaded": "reload_voice_identity",
    "operation_failed": "check_generation_pipeline",
    "operation_internal_error": "review_internal_failures",
    "status_unavailable": "check_status_operation",
    "metadata_unavailable": "check_metadata_operation",
}

_SUGGESTED_NEXT_ACTIONS: dict[str, str] = {
    "configuration_invalid": "verify_configuration",
    "configuration_migration_required": "run_configuration_migration",
    "storage_unavailable": "verify_storage_provider",
    "storage_permission_denied": "verify_storage_permissions",
    "voiceprint_registry_not_loaded": "reload_voice_identity",
    "voiceprint_artifact_missing": "regenerate_enrollment",
    "model_not_configured": "verify_model_configuration",
    "model_provider_unavailable": "restore_model_backend",
    "model_provider_not_loaded": "reload_voice_identity",
    "generation_orchestrator_not_loaded": "reload_generation_orchestrator",
    "operation_not_loaded": "reload_voice_identity",
    "operation_failed": "retry_generation_operation",
    "operation_internal_error": "manual_review_operation",
    "status_unavailable": "check_status_operation",
    "metadata_unavailable": "check_metadata_operation",
    "registry_inconsistent": "run_registry_reconciliation",
    "revision_inconsistent": "run_registry_reconciliation",
}

_RETRYABLE_REASON_CODES: set[str] = {
    "model_provider_unavailable",
    "model_provider_not_loaded",
    "operation_failed",
    "operation_not_loaded",
}

_REPAIRABLE_CANDIDATE_REASON_CODES: set[str] = {
    "voiceprint_artifact_missing",
    "artifact_missing",
    "metadata_invalid",
    "registry_inconsistent",
    "revision_inconsistent",
    "model_provider_unavailable",
    "model_provider_not_loaded",
    "operation_failed",
    "operation_internal_error",
    "operation_not_loaded",
}


@dataclass(slots=True, frozen=True)
class DiagnosticsContext:
    """Runtime context required for diagnostics projection."""

    entry_id: str
    runtime: Mapping[str, Any]


class VoiceIdentityDiagnosticsProvider:
    """Collect safe diagnostics from integration runtime state."""

    async def collect(self, *, context: DiagnosticsContext, source: str) -> dict[str, object]:
        health_summary = self._health_summary(context.runtime)
        capability_summary = self._capability_summary(context.runtime)
        model_summary = self._model_summary(context.runtime, health_summary)
        registry_summary = self._registry_summary(health_summary)
        generation_summary = self._generation_summary(health_summary)
        failure_summary = self._failure_summary(health_summary)
        config_summary = self._config_summary(context.runtime)

        payload = {
            "entry_id": safe_token(context.entry_id, "unknown_entry"),
            "source": safe_token(source, "unknown_source"),
            "platform": {
                "runtime_loaded": bool(context.runtime),
                "service_enabled": bool(config_summary.get("service_enabled", False)),
                "diagnostics_enabled": bool(config_summary.get("diagnostics_enabled", False)),
                "config_schema_version": config_summary.get("config_schema_version", 0),
                "health_state": health_summary.get("state", "unknown"),
                "health_reason_codes": health_summary.get("reason_codes", []),
            },
            "model": model_summary,
            "enrollment": {
                "model_preference": config_summary.get("model_preference", "unknown_model"),
                "supported_model_count": config_summary.get("supported_model_count", 0),
                "minimum_sample_count": config_summary.get("minimum_sample_count", 0),
                "maximum_sample_count": config_summary.get("maximum_sample_count", 0),
                "quality_threshold": config_summary.get("quality_threshold", 0.0),
            },
            "generation": generation_summary,
            "registry": registry_summary,
            "capability": capability_summary,
            "failure": failure_summary,
        }
        return sanitize_mapping(payload)

    def _config_summary(self, runtime: Mapping[str, Any]) -> dict[str, object]:
        manager = runtime.get(DATA_CONFIG_MANAGER)
        config = getattr(manager, "config", None)
        if config is None:
            return {
                "service_enabled": False,
                "diagnostics_enabled": False,
                "config_schema_version": 0,
                "model_preference": "unknown_model",
                "supported_model_count": 0,
                "minimum_sample_count": 0,
                "maximum_sample_count": 0,
                "quality_threshold": 0.0,
            }

        generation = getattr(config, "generation", None)
        diagnostics = getattr(config, "diagnostics", None)
        service = getattr(config, "service", None)
        supported_models = tuple(getattr(generation, "supported_models", ()) or ())

        return {
            "service_enabled": bool(getattr(service, "enabled", False)),
            "diagnostics_enabled": bool(getattr(diagnostics, "enabled", False)),
            "config_schema_version": int(getattr(config, "config_schema_version", 0) or 0),
            "model_preference": safe_token(getattr(generation, "model_preference", None), "unknown_model"),
            "supported_model_count": len(supported_models),
            "minimum_sample_count": int(getattr(generation, "min_sample_count", 0) or 0),
            "maximum_sample_count": int(getattr(generation, "max_sample_count", 0) or 0),
            "quality_threshold": float(getattr(generation, "quality_threshold", 0.0) or 0.0),
        }

    def _health_summary(self, runtime: Mapping[str, Any]) -> dict[str, object]:
        health_engine = runtime.get(DATA_HEALTH_ENGINE)
        snapshot = getattr(health_engine, "snapshot", None)
        if not callable(snapshot):
            return {
                "state": "unavailable",
                "reason_codes": ["health_engine_unavailable"],
                "components": {},
            }

        try:
            health = snapshot()
        except Exception:
            return {
                "state": "unavailable",
                "reason_codes": ["health_snapshot_failed"],
                "components": {},
            }

        components: dict[str, dict[str, object]] = {}
        for component in tuple(getattr(health, "components", ()) or ()):  # pragma: no branch
            name = safe_token(getattr(component, "component", None), "unknown_component")
            details = sanitize_mapping(dict(getattr(component, "details", {}) or {}))
            reason_codes = tuple(getattr(component, "reason_codes", ()) or ())
            components[name] = {
                "required": bool(getattr(component, "required", False)),
                "state": safe_token(str(getattr(component, "state", "unknown")), "unknown"),
                "reason_codes": sorted({normalize_reason_code(code) for code in reason_codes}),
                "details": details,
            }

        snapshot_reason_codes = tuple(getattr(health, "reason_codes", ()) or ())
        return {
            "state": safe_token(str(getattr(health, "state", "unknown")), "unknown"),
            "reason_codes": sorted({normalize_reason_code(code) for code in snapshot_reason_codes}),
            "components": components,
        }

    def _capability_summary(self, runtime: Mapping[str, Any]) -> dict[str, object]:
        registry = runtime.get(DATA_CAPABILITY_REGISTRY)
        snapshot = getattr(registry, "snapshot", None)
        if not callable(snapshot):
            return {
                "available": False,
                "registry_schema_version": 0,
                "config_schema_version": 0,
                "capability_count": 0,
                "enabled_count": 0,
                "diagnostics_capability_enabled": False,
            }

        try:
            payload = snapshot()
            capabilities = tuple(getattr(payload, "capabilities", ()) or ())
            enabled_count = len(tuple(item for item in capabilities if bool(getattr(item, "enabled", False))))
            diagnostics_enabled = any(
                safe_token(getattr(getattr(item, "descriptor", None), "name", None), "") == "diagnostics"
                and bool(getattr(item, "enabled", False))
                for item in capabilities
            )
            return {
                "available": True,
                "registry_schema_version": int(getattr(payload, "registry_schema_version", 0) or 0),
                "config_schema_version": int(getattr(payload, "config_schema_version", 0) or 0),
                "capability_count": len(capabilities),
                "enabled_count": enabled_count,
                "diagnostics_capability_enabled": diagnostics_enabled,
            }
        except Exception:
            return {
                "available": False,
                "registry_schema_version": 0,
                "config_schema_version": 0,
                "capability_count": 0,
                "enabled_count": 0,
                "diagnostics_capability_enabled": False,
            }

    def _model_summary(
        self,
        runtime: Mapping[str, Any],
        health_summary: Mapping[str, object],
    ) -> dict[str, object]:
        components = dict(health_summary.get("components", {}))
        model_component = dict(components.get("model_execution_provider", {}))
        details = dict(model_component.get("details", {}))
        return {
            "component_present": DATA_MODEL_EXECUTION_PROVIDER in runtime,
            "state": model_component.get("state", "unknown"),
            "reason_codes": model_component.get("reason_codes", []),
            "provider": safe_token(str(details.get("provider", "unknown_provider")), "unknown_provider"),
            "provider_available": bool(details.get("provider_available", False)),
        }

    def _generation_summary(self, health_summary: Mapping[str, object]) -> dict[str, object]:
        components = dict(health_summary.get("components", {}))
        orchestrator_component = dict(components.get("generation_orchestrator", {}))
        generate_component = dict(components.get("generate_voiceprint_operation", {}))
        status_component = dict(components.get("get_voiceprint_status_operation", {}))
        capabilities_component = dict(components.get("get_capabilities_operation", {}))
        return {
            "orchestrator_state": orchestrator_component.get("state", "unknown"),
            "orchestrator_reason_codes": orchestrator_component.get("reason_codes", []),
            "generate_operation_state": generate_component.get("state", "unknown"),
            "generate_operation_reason_codes": generate_component.get("reason_codes", []),
            "status_operation_state": status_component.get("state", "unknown"),
            "status_operation_reason_codes": status_component.get("reason_codes", []),
            "capabilities_operation_state": capabilities_component.get("state", "unknown"),
            "capabilities_operation_reason_codes": capabilities_component.get("reason_codes", []),
        }

    def _registry_summary(self, health_summary: Mapping[str, object]) -> dict[str, object]:
        components = dict(health_summary.get("components", {}))
        registry_component = dict(components.get("voiceprint_registry", {}))
        lifecycle_component = dict(components.get("voiceprint_lifecycle_manager", {}))
        revision_component = dict(components.get("voiceprint_revision_manager", {}))

        registry_details = dict(registry_component.get("details", {}))
        return {
            "registry_state": registry_component.get("state", "unknown"),
            "registry_reason_codes": registry_component.get("reason_codes", []),
            "record_count": int(registry_details.get("record_count", 0) or 0),
            "lifecycle_state": lifecycle_component.get("state", "unknown"),
            "lifecycle_reason_codes": lifecycle_component.get("reason_codes", []),
            "revision_state": revision_component.get("state", "unknown"),
            "revision_reason_codes": revision_component.get("reason_codes", []),
        }

    def _failure_summary(self, health_summary: Mapping[str, object]) -> dict[str, object]:
        components = dict(health_summary.get("components", {}))
        raw_reason_codes: list[str] = []
        for component_name in sorted(components):
            component = dict(components[component_name])
            state = safe_token(str(component.get("state", "unknown")), "unknown")
            if state == "healthy":
                continue
            raw_reason_codes.extend(str(code) for code in component.get("reason_codes", []))

        normalized = sorted({normalize_reason_code(code) for code in raw_reason_codes})
        hints = sorted({_REPAIR_HINTS.get(reason, "review_component_health") for reason in normalized})
        next_actions = sorted(
            {_SUGGESTED_NEXT_ACTIONS.get(reason, "review_component_health") for reason in normalized}
        )
        reason_code = normalized[0] if normalized else "no_issues"
        repair_hint_code = hints[0] if hints else "review_component_health"
        suggested_next_action_code = next_actions[0] if next_actions else "review_component_health"
        is_retryable = any(reason in _RETRYABLE_REASON_CODES for reason in normalized)
        is_repairable_candidate = any(reason in _REPAIRABLE_CANDIDATE_REASON_CODES for reason in normalized)
        return {
            "reason_code": reason_code,
            "repair_hint_code": repair_hint_code,
            "suggested_next_action_code": suggested_next_action_code,
            "is_retryable": is_retryable,
            "is_repairable_candidate": is_repairable_candidate,
            "issue_reason_codes": normalized,
            "repair_hint_codes": hints,
            "suggested_next_action_codes": next_actions,
        }


def build_runtime_context(
    *,
    runtime: Mapping[str, Any],
    entry_id: str,
) -> DiagnosticsContext:
    """Construct diagnostics context from runtime state."""
    return DiagnosticsContext(entry_id=entry_id, runtime=runtime)


def minimal_runtime_presence(runtime: Mapping[str, Any]) -> dict[str, bool]:
    """Return safe runtime presence booleans for diagnostics requests."""
    return {
        "has_voiceprint_registry": DATA_VOICEPRINT_REGISTRY in runtime,
        "has_lifecycle_manager": DATA_VOICEPRINT_LIFECYCLE_MANAGER in runtime,
        "has_revision_manager": DATA_VOICEPRINT_REVISION_MANAGER in runtime,
        "has_generation_orchestrator": DATA_GENERATION_ORCHESTRATOR in runtime,
        "has_generate_operation": DATA_GENERATE_VOICEPRINT_OPERATION in runtime,
        "has_status_operation": DATA_GET_VOICEPRINT_STATUS_OPERATION in runtime,
        "has_capabilities_operation": DATA_GET_CAPABILITIES_OPERATION in runtime,
        "has_health_telemetry_provider": DATA_HEALTH_TELEMETRY_PROVIDER in runtime,
    }
