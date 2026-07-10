"""Health and telemetry aggregation for Voice Identity runtime.

This module integrates existing health, diagnostics, and repair surfaces into
privacy-safe deterministic projections. It does not reimplement subsystem
authority or execute actions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    DATA_CAPABILITY_REGISTRY,
    DATA_HEALTH_ENGINE,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_REPAIR_RESOLVER,
)
from .diagnostics_provider import VoiceIdentityDiagnosticsProvider
from .diagnostics_sanitizer import normalize_reason_code, safe_token, sanitize_mapping
from .repair_resolver import VoiceIdentityRepairResolver


_NEXT_ACTIONS: dict[str, str] = {
    "health_ready": "no_action_required",
    "health_degraded": "review_component_health",
    "health_unavailable": "reload_voice_identity",
    "diagnostics_unavailable": "verify_diagnostics_configuration",
    "repair_framework_unavailable": "verify_repairs_configuration",
    "capability_registry_unavailable": "verify_capability_registry",
    "service_registry_unavailable": "reload_voice_identity",
    "model_backend_unavailable": "restore_model_backend",
    "model_provider_unavailable": "restore_model_backend",
    "model_provider_not_loaded": "reload_voice_identity",
    "storage_provider_unavailable": "verify_storage_provider",
    "registry_unavailable": "verify_registry_runtime",
    "lifecycle_unavailable": "verify_lifecycle_runtime",
    "operation_failed": "check_generation_pipeline",
    "generation_model_failed": "restore_model_backend",
    "compatibility_readiness_unavailable": "review_component_health",
    "internal_error": "review_component_health",
}


@dataclass(slots=True, frozen=True)
class HealthTelemetryContext:
    """Runtime context for health and telemetry aggregation."""

    entry_id: str
    runtime: Mapping[str, Any]


class VoiceIdentityHealthTelemetryProvider:
    """Deterministic health and telemetry aggregator."""

    def __init__(self) -> None:
        self._diagnostics_provider = VoiceIdentityDiagnosticsProvider()
        self._loaded = True
        self._cleared = False

    async def collect_health(
        self,
        *,
        context: HealthTelemetryContext,
        services_registered: bool,
    ) -> dict[str, object]:
        """Collect health projection for service consumers."""
        if not self._loaded:
            return self._unavailable_health(
                entry_id=context.entry_id,
                reason_code="health_unavailable",
            )

        try:
            health = self._health_summary(context.runtime)
            diagnostics = await self._diagnostics_status(context)
            repairs = self._repair_status(context.runtime, diagnostics.get("failure_summary"))
            readiness = self._readiness_summary(health)

            status = safe_token(str(health.get("state", "unavailable")), "unavailable")
            reason_code = _overall_reason_code(health_summary=health, status=status)

            payload = {
                "entry_id": safe_token(context.entry_id, "unknown_entry"),
                "status": status,
                "reason_code": reason_code,
                "is_healthy": status == "healthy",
                "is_degraded": status == "degraded",
                "is_available": status != "unavailable",
                "is_recoverable": bool(repairs.get("repair_available", False)) or bool(
                    diagnostics.get("available", False)
                ),
                "diagnostic_available": bool(diagnostics.get("available", False)),
                "repair_available": bool(repairs.get("repair_available", False)),
                "repair_hint_code": safe_token(
                    str(repairs.get("repair_hint_code", "review_component_health")),
                    "review_component_health",
                ),
                "suggested_next_action_code": _NEXT_ACTIONS.get(
                    reason_code,
                    safe_token(
                        str(repairs.get("suggested_next_action_code", "review_component_health")),
                        "review_component_health",
                    ),
                ),
                "service_registry": {
                    "services_registered": services_registered,
                    "reason_code": "service_registry_ready"
                    if services_registered
                    else "service_registry_unavailable",
                },
                "component_status": self._component_projection(
                    health_summary=health,
                    diagnostic_available=bool(diagnostics.get("available", False)),
                    repair_available=bool(repairs.get("repair_available", False)),
                ),
                "diagnostics_status": {
                    "available": bool(diagnostics.get("available", False)),
                    "reason_code": safe_token(
                        str(diagnostics.get("reason_code", "diagnostics_unavailable")),
                        "diagnostics_unavailable",
                    ),
                },
                "repair_status": {
                    "available": bool(repairs.get("repair_available", False)),
                    "reason_code": safe_token(
                        str(repairs.get("reason_code", "repair_framework_unavailable")),
                        "repair_framework_unavailable",
                    ),
                },
                "readiness": readiness,
            }
            return sanitize_mapping(payload)
        except Exception:
            return self._unavailable_health(
                entry_id=context.entry_id,
                reason_code="internal_error",
            )

    async def collect_telemetry(
        self,
        *,
        context: HealthTelemetryContext,
        services_registered: bool,
    ) -> dict[str, object]:
        """Collect privacy-safe operational telemetry projection."""
        health_payload = await self.collect_health(
            context=context,
            services_registered=services_registered,
        )
        health_status = safe_token(str(health_payload.get("status", "unavailable")), "unavailable")
        telemetry_status = "telemetry_ready" if health_status == "healthy" else "telemetry_degraded"

        try:
            capability_status = self._capability_status(context.runtime)
            payload = {
                "entry_id": health_payload.get("entry_id", "unknown_entry"),
                "status": telemetry_status,
                "reason_code": telemetry_status,
                "component_status": health_payload.get("component_status", []),
                "service_status": {
                    "services_registered": services_registered,
                    "get_health": services_registered,
                    "get_telemetry": services_registered,
                    "get_diagnostics": services_registered,
                    "get_repairs": services_registered,
                },
                "capability_status": capability_status,
                "diagnostics_status": health_payload.get("diagnostics_status", {}),
                "repair_status": health_payload.get("repair_status", {}),
                "compatibility_readiness": health_payload.get("readiness", {}).get(
                    "compatibility_readiness",
                    "unavailable",
                ),
                "attribution_readiness": health_payload.get("readiness", {}).get(
                    "attribution_readiness",
                    "unavailable",
                ),
            }
            return sanitize_mapping(payload)
        except Exception:
            return sanitize_mapping(
                {
                    "entry_id": safe_token(context.entry_id, "unknown_entry"),
                    "status": "telemetry_unavailable",
                    "reason_code": "internal_error",
                    "component_status": [],
                    "service_status": {
                        "services_registered": services_registered,
                    },
                    "capability_status": {
                        "available": False,
                        "reason_code": "capability_registry_unavailable",
                    },
                    "diagnostics_status": {
                        "available": False,
                        "reason_code": "diagnostics_unavailable",
                    },
                    "repair_status": {
                        "available": False,
                        "reason_code": "repair_framework_unavailable",
                    },
                    "compatibility_readiness": "unavailable",
                    "attribution_readiness": "unavailable",
                }
            )

    def clear(self) -> None:
        """Clear provider lifecycle state for unload."""
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        """Return clear marker for lifecycle tests."""
        return self._cleared

    def _health_summary(self, runtime: Mapping[str, Any]) -> dict[str, object]:
        health_engine = runtime.get(DATA_HEALTH_ENGINE)
        snapshot = getattr(health_engine, "snapshot", None)
        if not callable(snapshot):
            return {
                "state": "unavailable",
                "reason_codes": ["health_unavailable"],
                "components": {},
            }

        try:
            health = snapshot()
        except Exception:
            return {
                "state": "unavailable",
                "reason_codes": ["internal_error"],
                "components": {},
            }

        components: dict[str, dict[str, object]] = {}
        for component in tuple(getattr(health, "components", ()) or ()):  # pragma: no branch
            name = safe_token(getattr(component, "component", None), "unknown_component")
            reason_codes = tuple(getattr(component, "reason_codes", ()) or ())
            components[name] = {
                "required": bool(getattr(component, "required", False)),
                "state": safe_token(str(getattr(component, "state", "unknown")), "unknown"),
                "reason_codes": sorted({normalize_reason_code(code) for code in reason_codes}),
            }

        snapshot_reason_codes = tuple(getattr(health, "reason_codes", ()) or ())
        return {
            "state": safe_token(str(getattr(health, "state", "unknown")), "unknown"),
            "reason_codes": sorted({normalize_reason_code(code) for code in snapshot_reason_codes}),
            "components": components,
        }

    async def _diagnostics_status(self, context: HealthTelemetryContext) -> dict[str, object]:
        try:
            diagnostics = await self._diagnostics_provider.collect(
                context=context,
                source="health_telemetry",
            )
            platform = diagnostics.get("platform", {})
            available = bool(platform.get("diagnostics_enabled", False))
            failure_summary = diagnostics.get("failure")
            return {
                "available": available,
                "reason_code": "diagnostics_ready" if available else "diagnostics_unavailable",
                "failure_summary": failure_summary if isinstance(failure_summary, dict) else None,
            }
        except Exception:
            return {
                "available": False,
                "reason_code": "diagnostics_unavailable",
                "failure_summary": None,
            }

    def _repair_status(
        self,
        runtime: Mapping[str, Any],
        failure_summary: Mapping[str, object] | None,
    ) -> dict[str, object]:
        resolver = runtime.get(DATA_REPAIR_RESOLVER)
        if not isinstance(resolver, VoiceIdentityRepairResolver):
            return {
                "repair_available": False,
                "reason_code": "repair_framework_unavailable",
                "repair_hint_code": "review_component_health",
                "suggested_next_action_code": "verify_repairs_configuration",
            }

        try:
            resolved = resolver.resolve(failure_summary)
            projected = resolved.to_dict()
            return {
                "repair_available": bool(projected.get("repairable", False)),
                "reason_code": safe_token(str(projected.get("reason_code", "repair_framework_unavailable")),
                                           "repair_framework_unavailable"),
                "repair_hint_code": safe_token(
                    str(projected.get("repair_hint_code", "review_component_health")),
                    "review_component_health",
                ),
                "suggested_next_action_code": safe_token(
                    str(projected.get("suggested_next_action_code", "review_component_health")),
                    "review_component_health",
                ),
            }
        except Exception:
            return {
                "repair_available": False,
                "reason_code": "repair_framework_unavailable",
                "repair_hint_code": "review_component_health",
                "suggested_next_action_code": "verify_repairs_configuration",
            }

    def _component_projection(
        self,
        *,
        health_summary: Mapping[str, object],
        diagnostic_available: bool,
        repair_available: bool,
    ) -> list[dict[str, object]]:
        components = dict(health_summary.get("components", {}))
        projection: list[dict[str, object]] = []
        for name in sorted(components):
            component = dict(components[name])
            state = safe_token(str(component.get("state", "unknown")), "unknown")
            reason_codes = tuple(component.get("reason_codes", ()))
            reason_code = _primary_reason_code(reason_codes)
            projection.append(
                {
                    "component": name,
                    "component_type": _component_type(name),
                    "status": state,
                    "reason_code": reason_code,
                    "is_healthy": state == "healthy",
                    "is_degraded": state == "degraded",
                    "is_available": state != "unavailable",
                    "is_recoverable": repair_available,
                    "diagnostic_available": diagnostic_available,
                    "repair_available": repair_available,
                    "suggested_next_action_code": _NEXT_ACTIONS.get(
                        reason_code,
                        "review_component_health",
                    ),
                }
            )
        return projection

    def _capability_status(self, runtime: Mapping[str, Any]) -> dict[str, object]:
        registry = runtime.get(DATA_CAPABILITY_REGISTRY)
        snapshot = getattr(registry, "snapshot", None)
        if not callable(snapshot):
            return {
                "available": False,
                "reason_code": "capability_registry_unavailable",
                "registry_schema_version": 0,
                "config_schema_version": 0,
                "capability_count": 0,
                "implemented_count": 0,
                "enabled_count": 0,
            }

        try:
            payload = snapshot()
            capabilities = tuple(getattr(payload, "capabilities", ()) or ())
            implemented_count = len(
                tuple(
                    item
                    for item in capabilities
                    if safe_token(str(getattr(getattr(item, "descriptor", None), "maturity", "")), "")
                    == "implemented"
                )
            )
            enabled_count = len(tuple(item for item in capabilities if bool(getattr(item, "enabled", False))))
            return {
                "available": True,
                "reason_code": "capability_registry_ready",
                "registry_schema_version": int(getattr(payload, "registry_schema_version", 0) or 0),
                "config_schema_version": int(getattr(payload, "config_schema_version", 0) or 0),
                "capability_count": len(capabilities),
                "implemented_count": implemented_count,
                "enabled_count": enabled_count,
            }
        except Exception:
            return {
                "available": False,
                "reason_code": "capability_registry_unavailable",
                "registry_schema_version": 0,
                "config_schema_version": 0,
                "capability_count": 0,
                "implemented_count": 0,
                "enabled_count": 0,
            }

    def _readiness_summary(self, health_summary: Mapping[str, object]) -> dict[str, str]:
        components = dict(health_summary.get("components", {}))
        attribution_dependencies = (
            "model_execution_provider",
            "voiceprint_registry",
            "voiceprint_lifecycle_manager",
            "voiceprint_revision_manager",
        )
        compatibility_dependencies = (
            "storage_provider",
            "model_execution_provider",
            "voiceprint_registry",
            "voiceprint_lifecycle_manager",
            "voiceprint_revision_manager",
            "get_capabilities_operation",
        )
        return {
            "attribution_readiness": _readiness_state(components, attribution_dependencies),
            "compatibility_readiness": _readiness_state(components, compatibility_dependencies),
        }

    def _unavailable_health(self, *, entry_id: str, reason_code: str) -> dict[str, object]:
        return sanitize_mapping(
            {
                "entry_id": safe_token(entry_id, "unknown_entry"),
                "status": "unavailable",
                "reason_code": reason_code,
                "is_healthy": False,
                "is_degraded": False,
                "is_available": False,
                "is_recoverable": False,
                "diagnostic_available": False,
                "repair_available": False,
                "repair_hint_code": "review_component_health",
                "suggested_next_action_code": _NEXT_ACTIONS.get(reason_code, "review_component_health"),
                "service_registry": {
                    "services_registered": False,
                    "reason_code": "service_registry_unavailable",
                },
                "component_status": [],
                "diagnostics_status": {
                    "available": False,
                    "reason_code": "diagnostics_unavailable",
                },
                "repair_status": {
                    "available": False,
                    "reason_code": "repair_framework_unavailable",
                },
                "readiness": {
                    "attribution_readiness": "unavailable",
                    "compatibility_readiness": "unavailable",
                },
            }
        )


def build_health_telemetry_context(
    *,
    runtime: Mapping[str, Any],
    entry_id: str,
) -> HealthTelemetryContext:
    """Construct health/telemetry context from runtime state."""
    return HealthTelemetryContext(entry_id=entry_id, runtime=runtime)


def _primary_reason_code(reason_codes: object) -> str:
    if not isinstance(reason_codes, list | tuple):
        return "unknown_reason"
    if not reason_codes:
        return "health_ready"
    return normalize_reason_code(str(reason_codes[0]))


def _overall_reason_code(*, health_summary: Mapping[str, object], status: str) -> str:
    if status == "healthy":
        return "health_ready"

    components = dict(health_summary.get("components", {}))
    if status in {"unavailable", "degraded"}:
        for component_name in sorted(components):
            component = dict(components[component_name])
            component_state = safe_token(str(component.get("state", "unknown")), "unknown")
            if component_state != status:
                continue
            reason_codes = tuple(component.get("reason_codes", ()))
            reason = _primary_reason_code(reason_codes)
            if reason != "unknown_reason":
                return reason

    aggregated_reason = _primary_reason_code(health_summary.get("reason_codes"))
    if aggregated_reason != "unknown_reason":
        return aggregated_reason

    if status == "degraded":
        return "health_degraded"
    if status == "unavailable":
        return "health_unavailable"
    return "health_unavailable"


def _component_type(component: str) -> str:
    if component in {"integration_runtime", "configuration_manager"}:
        return "runtime"
    if "capability" in component:
        return "capability"
    if "diagnostics" in component:
        return "diagnostics"
    if "repair" in component:
        return "repairs"
    if "model" in component:
        return "model"
    if "storage" in component or "artifact" in component:
        return "storage"
    if "registry" in component or "lifecycle" in component or "revision" in component:
        return "lifecycle"
    if "operation" in component:
        return "operations"
    if "provider" in component:
        return "provider"
    return "runtime"


def _readiness_state(
    components: Mapping[str, dict[str, object]],
    dependency_names: tuple[str, ...],
) -> str:
    if not dependency_names:
        return "unavailable"

    states: list[str] = []
    for name in dependency_names:
        component = components.get(name)
        if not isinstance(component, dict):
            return "unavailable"
        states.append(safe_token(str(component.get("state", "unknown")), "unknown"))

    if any(state == "unavailable" for state in states):
        return "unavailable"
    if any(state == "degraded" for state in states):
        return "degraded"
    if all(state == "healthy" for state in states):
        return "ready"
    return "unavailable"
