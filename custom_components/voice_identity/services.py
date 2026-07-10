"""Service registration for Voice Identity integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall, SupportsResponse

from .attribution_service import AttributionRequest, SpeakerAttributionFoundation, create_attribution_request
from .const import DATA_ATTRIBUTION_FOUNDATION
from .const import DATA_IDENTITY_CONTEXT_GENERATOR
from .const import DOMAIN
from .const import DATA_HEALTH_TELEMETRY_PROVIDER
from .const import DATA_REPAIR_RESOLVER
from .diagnostics_provider import (
    VoiceIdentityDiagnosticsProvider,
    build_runtime_context,
    minimal_runtime_presence,
)
from .health_telemetry import (
    VoiceIdentityHealthTelemetryProvider,
    build_health_telemetry_context,
)
from .identity_context import IdentityContextGenerator
from .repair_resolver import VoiceIdentityRepairResolver
from .repair_registry import VoiceIdentityRepairRegistry

SERVICE_GET_DIAGNOSTICS = "get_diagnostics"
SERVICE_GET_REPAIRS = "get_repairs"
SERVICE_GET_HEALTH = "get_health"
SERVICE_GET_TELEMETRY = "get_telemetry"
SERVICE_ATTRIBUTE_SPEAKER = "attribute_speaker"
SERVICE_GET_IDENTITY_CONTEXT = "get_identity_context"
_SERVICES_REGISTERED_KEY = "_services_registered"

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_DIAGNOSTICS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)

SERVICE_GET_REPAIRS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)

SERVICE_GET_HEALTH_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)

SERVICE_GET_TELEMETRY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)

SERVICE_ATTRIBUTE_SPEAKER_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("audio_ref"): str,
        vol.Optional("candidate_scope"): [str],
        vol.Optional("model_preference"): str,
    }
)

SERVICE_GET_IDENTITY_CONTEXT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("audio_ref"): str,
        vol.Optional("candidate_scope"): [str],
        vol.Optional("model_preference"): str,
    }
)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register Voice Identity services."""
    domain_bucket = hass.data.setdefault(DOMAIN, {})
    if domain_bucket.get(_SERVICES_REGISTERED_KEY):
        return

    provider = VoiceIdentityDiagnosticsProvider()

    async def _handle_get_diagnostics(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "diagnostics": {
                    "runtime_loaded": False,
                },
            }

        payload = await provider.collect(
            context=build_runtime_context(entry_id=runtime_entry_id, runtime=runtime),
            source="service_get_diagnostics",
        )
        payload["runtime_presence"] = minimal_runtime_presence(runtime)
        return {
            "success": True,
            "reason_code": "ready",
            "entry_id": runtime_entry_id,
            "diagnostics": payload,
        }

    async def _handle_get_repairs(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "repairs": {
                    "status": "diagnostics_unavailable",
                    "repairable": False,
                    "retryable": False,
                    "reason_code": "diagnostics_unavailable",
                    "repair_hint_code": "review_component_health",
                    "suggested_next_action_code": "reload_voice_identity",
                    "repairs": [],
                },
            }

        try:
            diagnostics_payload = await provider.collect(
                context=build_runtime_context(entry_id=runtime_entry_id, runtime=runtime),
                source="service_get_repairs",
            )
            failure_summary = diagnostics_payload.get("failure")

            resolver = runtime.get(DATA_REPAIR_RESOLVER)
            if not isinstance(resolver, VoiceIdentityRepairResolver):
                resolver = VoiceIdentityRepairResolver(registry=VoiceIdentityRepairRegistry.with_defaults())

            resolved = resolver.resolve(failure_summary if isinstance(failure_summary, dict) else None)
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "repairs": resolved.to_dict(),
            }
        except Exception:
            _LOGGER.exception("voice_identity.get_repairs failed closed")
            return {
                "success": False,
                "reason_code": "diagnostics_unavailable",
                "entry_id": runtime_entry_id,
                "repairs": {
                    "status": "diagnostics_unavailable",
                    "repairable": False,
                    "retryable": False,
                    "reason_code": "diagnostics_unavailable",
                    "repair_hint_code": "review_component_health",
                    "suggested_next_action_code": "reload_voice_identity",
                    "repairs": [],
                },
            }

    async def _handle_get_health(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "health": {
                    "status": "unavailable",
                    "reason_code": "health_unavailable",
                    "diagnostic_available": False,
                    "repair_available": False,
                    "readiness": {
                        "attribution_readiness": "unavailable",
                        "compatibility_readiness": "unavailable",
                    },
                },
            }

        provider_obj = runtime.get(DATA_HEALTH_TELEMETRY_PROVIDER)
        provider = (
            provider_obj
            if isinstance(provider_obj, VoiceIdentityHealthTelemetryProvider)
            else VoiceIdentityHealthTelemetryProvider()
        )
        try:
            payload = await provider.collect_health(
                context=build_health_telemetry_context(entry_id=runtime_entry_id, runtime=runtime),
                services_registered=bool(hass.data.get(DOMAIN, {}).get(_SERVICES_REGISTERED_KEY, False)),
            )
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "health": payload,
            }
        except Exception:
            _LOGGER.exception("voice_identity.get_health failed closed")
            return {
                "success": False,
                "reason_code": "health_unavailable",
                "entry_id": runtime_entry_id,
                "health": {
                    "status": "unavailable",
                    "reason_code": "internal_error",
                    "diagnostic_available": False,
                    "repair_available": False,
                    "readiness": {
                        "attribution_readiness": "unavailable",
                        "compatibility_readiness": "unavailable",
                    },
                },
            }

    async def _handle_get_telemetry(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "telemetry": {
                    "status": "telemetry_unavailable",
                    "reason_code": "telemetry_unavailable",
                    "component_status": [],
                    "compatibility_readiness": "unavailable",
                    "attribution_readiness": "unavailable",
                },
            }

        provider_obj = runtime.get(DATA_HEALTH_TELEMETRY_PROVIDER)
        provider = (
            provider_obj
            if isinstance(provider_obj, VoiceIdentityHealthTelemetryProvider)
            else VoiceIdentityHealthTelemetryProvider()
        )
        try:
            payload = await provider.collect_telemetry(
                context=build_health_telemetry_context(entry_id=runtime_entry_id, runtime=runtime),
                services_registered=bool(hass.data.get(DOMAIN, {}).get(_SERVICES_REGISTERED_KEY, False)),
            )
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "telemetry": payload,
            }
        except Exception:
            _LOGGER.exception("voice_identity.get_telemetry failed closed")
            return {
                "success": False,
                "reason_code": "telemetry_unavailable",
                "entry_id": runtime_entry_id,
                "telemetry": {
                    "status": "telemetry_unavailable",
                    "reason_code": "internal_error",
                    "component_status": [],
                    "compatibility_readiness": "unavailable",
                    "attribution_readiness": "unavailable",
                },
            }

    async def _handle_attribute_speaker(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "attribution": {
                    "success": True,
                    "status": "attribution_unavailable",
                    "identity_confidence_level": "unknown",
                    "confidence": 0.0,
                    "confidence_band": "unavailable",
                    "reason_code": "attribution_unavailable",
                    "attribution_method": "none",
                    "is_confident": False,
                    "is_ambiguous": False,
                    "is_abstained": True,
                    "diagnostic_summary": {
                        "diagnostic_available": False,
                        "diagnostic_reason_code": "diagnostics_unavailable",
                        "repair_available": False,
                        "health_status": "unavailable",
                        "attribution_readiness": "unavailable",
                        "compatibility_readiness": "unavailable",
                    },
                    "repair_hint_code": "review_component_health",
                    "suggested_next_action_code": "reload_voice_identity",
                    "health_status": "unavailable",
                    "readiness_status": "unavailable",
                },
            }

        request: AttributionRequest = create_attribution_request(call.data)
        foundation_obj = runtime.get(DATA_ATTRIBUTION_FOUNDATION)
        foundation = (
            foundation_obj
            if isinstance(foundation_obj, SpeakerAttributionFoundation)
            else SpeakerAttributionFoundation()
        )

        try:
            result = await foundation.attribute(
                entry_id=runtime_entry_id,
                runtime=runtime,
                request=request,
                services_registered=bool(hass.data.get(DOMAIN, {}).get(_SERVICES_REGISTERED_KEY, False)),
            )
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "attribution": result.to_dict(),
            }
        except Exception:
            _LOGGER.exception("voice_identity.attribute_speaker failed closed")
            return {
                "success": False,
                "reason_code": "attribution_unavailable",
                "entry_id": runtime_entry_id,
                "attribution": {
                    "success": True,
                    "status": "attribution_unavailable",
                    "identity_confidence_level": "unknown",
                    "confidence": 0.0,
                    "confidence_band": "unavailable",
                    "reason_code": "internal_error",
                    "attribution_method": "none",
                    "is_confident": False,
                    "is_ambiguous": False,
                    "is_abstained": True,
                    "diagnostic_summary": {
                        "diagnostic_available": False,
                        "diagnostic_reason_code": "diagnostics_unavailable",
                        "repair_available": False,
                        "health_status": "unavailable",
                        "attribution_readiness": "unavailable",
                        "compatibility_readiness": "unavailable",
                    },
                    "repair_hint_code": "review_component_health",
                    "suggested_next_action_code": "reload_voice_identity",
                    "health_status": "unavailable",
                    "readiness_status": "unavailable",
                },
            }

    async def _handle_get_identity_context(call: ServiceCall) -> dict[str, object]:
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "identity_context": {
                    "state": "unavailable",
                    "reason_code": "attribution_unavailable",
                    "source": "voice_identity",
                },
            }

        request: AttributionRequest = create_attribution_request(call.data)
        foundation_obj = runtime.get(DATA_ATTRIBUTION_FOUNDATION)
        foundation = (
            foundation_obj
            if isinstance(foundation_obj, SpeakerAttributionFoundation)
            else SpeakerAttributionFoundation()
        )
        generator_obj = runtime.get(DATA_IDENTITY_CONTEXT_GENERATOR)
        generator = (
            generator_obj
            if isinstance(generator_obj, IdentityContextGenerator)
            else IdentityContextGenerator()
        )

        try:
            attribution = await foundation.attribute(
                entry_id=runtime_entry_id,
                runtime=runtime,
                request=request,
                services_registered=bool(hass.data.get(DOMAIN, {}).get(_SERVICES_REGISTERED_KEY, False)),
            )
            context = generator.generate(attribution=attribution)
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "identity_context": generator.to_dict(context=context),
            }
        except Exception:
            _LOGGER.exception("voice_identity.get_identity_context failed closed")
            return {
                "success": False,
                "reason_code": "identity_context_unavailable",
                "entry_id": runtime_entry_id,
                "identity_context": {
                    "state": "unavailable",
                    "reason_code": "internal_error",
                    "source": "voice_identity",
                },
            }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DIAGNOSTICS,
        _handle_get_diagnostics,
        schema=SERVICE_GET_DIAGNOSTICS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_REPAIRS,
        _handle_get_repairs,
        schema=SERVICE_GET_REPAIRS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HEALTH,
        _handle_get_health,
        schema=SERVICE_GET_HEALTH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_TELEMETRY,
        _handle_get_telemetry,
        schema=SERVICE_GET_TELEMETRY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ATTRIBUTE_SPEAKER,
        _handle_attribute_speaker,
        schema=SERVICE_ATTRIBUTE_SPEAKER_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_IDENTITY_CONTEXT,
        _handle_get_identity_context,
        schema=SERVICE_GET_IDENTITY_CONTEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    domain_bucket[_SERVICES_REGISTERED_KEY] = True


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Voice Identity services."""
    domain_bucket = hass.data.get(DOMAIN)
    if not isinstance(domain_bucket, dict):
        return
    if not domain_bucket.get(_SERVICES_REGISTERED_KEY):
        return

    hass.services.async_remove(DOMAIN, SERVICE_GET_DIAGNOSTICS)
    hass.services.async_remove(DOMAIN, SERVICE_GET_REPAIRS)
    hass.services.async_remove(DOMAIN, SERVICE_GET_HEALTH)
    hass.services.async_remove(DOMAIN, SERVICE_GET_TELEMETRY)
    hass.services.async_remove(DOMAIN, SERVICE_ATTRIBUTE_SPEAKER)
    hass.services.async_remove(DOMAIN, SERVICE_GET_IDENTITY_CONTEXT)
    domain_bucket[_SERVICES_REGISTERED_KEY] = False


def _resolve_runtime(
    hass: HomeAssistant,
    requested_entry_id: str,
) -> tuple[str | None, dict[str, object] | None]:
    domain_bucket = hass.data.get(DOMAIN)
    if not isinstance(domain_bucket, dict):
        return None, None

    if requested_entry_id:
        runtime = domain_bucket.get(requested_entry_id)
        if isinstance(runtime, dict):
            return requested_entry_id, runtime
        return None, None

    entry_ids = sorted(
        key
        for key, value in domain_bucket.items()
        if key != _SERVICES_REGISTERED_KEY and isinstance(value, dict)
    )
    if not entry_ids:
        return None, None

    selected = entry_ids[0]
    runtime = domain_bucket.get(selected)
    if not isinstance(runtime, dict):
        return None, None
    return selected, runtime
