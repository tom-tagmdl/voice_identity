"""Service registration for Voice Identity integration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall, SupportsResponse

from .attribution_context_store import InMemoryAttributionContextStore
from .attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
    ConfidenceBand,
    IdentityConfidenceLevel,
)
from .attribution_service import (
    AttributionRequest,
    SpeakerAttributionFoundation,
    build_runtime_attribution_record,
    create_attribution_request,
)
from .const import DATA_ATTRIBUTION_FOUNDATION
from .const import DATA_ATTRIBUTION_CONTEXT_STORE
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
        vol.Optional("conversation_id"): str,
        vol.Optional("device_id"): str,
        vol.Optional("satellite_id"): str,
        vol.Optional("room_id"): str,
        vol.Optional("turn_index"): vol.Coerce(int),
        vol.Optional("pipeline_id"): str,
    }
)

SERVICE_GET_IDENTITY_CONTEXT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("audio_ref"): str,
        vol.Optional("candidate_scope"): [str],
        vol.Optional("model_preference"): str,
        vol.Optional("conversation_id"): str,
        vol.Optional("device_id"): str,
        vol.Optional("satellite_id"): str,
        vol.Optional("room_id"): str,
        vol.Optional("turn_index"): vol.Coerce(int),
        vol.Optional("pipeline_id"): str,
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
        request: AttributionRequest = create_attribution_request(call.data)
        correlation = request.correlation_payload()
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "correlation": correlation,
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
            persisted_record = _persist_runtime_record(
                runtime=runtime,
                request=request,
                attribution=result,
            )
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "correlation": correlation,
                "attribution": result.to_dict(),
                "runtime_attribution": _project_runtime_attribution(persisted_record),
            }
        except Exception:
            _LOGGER.exception("voice_identity.attribute_speaker failed closed")
            fallback = _unavailable_attribution(reason_code="internal_error")
            persisted_record = _persist_runtime_record(
                runtime=runtime,
                request=request,
                attribution=fallback,
            )
            return {
                "success": False,
                "reason_code": "attribution_unavailable",
                "entry_id": runtime_entry_id,
                "correlation": correlation,
                "attribution": {
                    **fallback.to_dict(),
                },
                "runtime_attribution": _project_runtime_attribution(persisted_record),
            }

    async def _handle_get_identity_context(call: ServiceCall) -> dict[str, object]:
        request: AttributionRequest = create_attribution_request(call.data)
        correlation = request.correlation_payload()
        requested_entry_id = str(call.data.get("entry_id", "") or "").strip()
        runtime_entry_id, runtime = _resolve_runtime(hass, requested_entry_id)
        if runtime is None or runtime_entry_id is None:
            return {
                "success": False,
                "reason_code": "runtime_unavailable",
                "entry_id": requested_entry_id or "unknown_entry",
                "correlation": correlation,
                "identity_context": {
                    "state": "unavailable",
                    "reason_code": "attribution_unavailable",
                    "source": "voice_identity",
                },
            }

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

        store = _resolve_context_store(runtime)
        now = _utcnow()
        store.sweep_expired(now=now)

        resolved_record = store.resolve_current_speaker(
            conversation_id=request.conversation_id,
            device_id=request.device_id,
            satellite_id=request.satellite_id,
            room_id=request.room_id,
            now=now,
        )
        if resolved_record is not None:
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "correlation": correlation,
                "runtime_attribution": _project_runtime_attribution(resolved_record),
                "identity_context": _identity_context_from_record(record=resolved_record),
            }

        try:
            if not request.has_audio_evidence():
                return {
                    "success": True,
                    "reason_code": "ready",
                    "entry_id": runtime_entry_id,
                    "correlation": correlation,
                    "identity_context": {
                        "state": "unknown",
                        "person_id": None,
                        "voice_profile_id": None,
                        "confidence": None,
                        "confidence_band": None,
                        "reason_code": "identity_context_missing",
                        "source": "voice_identity",
                    },
                }

            attribution = await foundation.attribute(
                entry_id=runtime_entry_id,
                runtime=runtime,
                request=request,
                services_registered=bool(hass.data.get(DOMAIN, {}).get(_SERVICES_REGISTERED_KEY, False)),
            )
            persisted_record = _persist_runtime_record(
                runtime=runtime,
                request=request,
                attribution=attribution,
            )
            resolved_after = store.resolve_current_speaker(
                conversation_id=request.conversation_id,
                device_id=request.device_id,
                satellite_id=request.satellite_id,
                room_id=request.room_id,
                now=_utcnow(),
            )
            context_payload = (
                _identity_context_from_record(record=resolved_after)
                if resolved_after is not None
                else generator.to_dict(context=generator.generate(attribution=attribution))
            )
            return {
                "success": True,
                "reason_code": "ready",
                "entry_id": runtime_entry_id,
                "correlation": correlation,
                "runtime_attribution": _project_runtime_attribution(
                    resolved_after if resolved_after is not None else persisted_record
                ),
                "identity_context": context_payload,
            }
        except Exception:
            _LOGGER.exception("voice_identity.get_identity_context failed closed")
            fallback = _unavailable_attribution(reason_code="internal_error")
            persisted_record = _persist_runtime_record(
                runtime=runtime,
                request=request,
                attribution=fallback,
            )
            return {
                "success": False,
                "reason_code": "identity_context_unavailable",
                "entry_id": runtime_entry_id,
                "correlation": correlation,
                "runtime_attribution": _project_runtime_attribution(persisted_record),
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_context_store(runtime: dict[str, object]) -> InMemoryAttributionContextStore:
    store_obj = runtime.get(DATA_ATTRIBUTION_CONTEXT_STORE)
    if isinstance(store_obj, InMemoryAttributionContextStore):
        return store_obj

    # Preserve current runtime behavior even when older runtime fixtures omit the store.
    store = InMemoryAttributionContextStore()
    runtime[DATA_ATTRIBUTION_CONTEXT_STORE] = store
    return store


def _project_runtime_attribution(record) -> dict[str, object]:
    return {
        "attribution_id": record.attribution_id,
        "issued_at_utc": record.issued_at_utc,
        "expires_at_utc": record.expires_at_utc,
        "state": record.decision.state,
        "reason_code": record.decision.reason_code,
        "recommended_action": record.decision.recommended_action,
        "confidence_band": record.confidence.band,
        "freshness_class": record.freshness.freshness_class,
        "attribution_age_ms": record.freshness.attribution_age_ms,
        "valid_until_utc": record.freshness.valid_until_utc,
        "correlation": {
            "conversation_id": record.binding.conversation_id,
            "device_id": record.binding.device_id,
            "satellite_id": record.binding.satellite_id,
            "room_id": record.binding.room_id,
            "turn_index": record.binding.turn_index,
            "pipeline_id": record.binding.pipeline_id,
        },
    }


def _identity_context_from_record(
    *,
    record,
) -> dict[str, object]:
    state_map = {
        "known": "known",
        "ambiguous": "low_confidence",
        "unknown": "unknown",
        "unavailable": "unavailable",
        "not_required": "not_required",
    }
    state = state_map.get(record.decision.state, "unknown")

    context = {
        "state": state,
        "person_id": record.subject.person_id if state == "known" else None,
        "voice_profile_id": record.subject.profile_id if state == "known" else None,
        "confidence": record.confidence.score if state in {"known", "low_confidence"} else None,
        "confidence_band": record.confidence.band if state in {"known", "low_confidence"} else None,
        "reason_code": record.decision.reason_code,
        "source": "voice_identity",
        "generated_at": _utcnow().isoformat(),
    }
    return context


def _unavailable_attribution(*, reason_code: str) -> AttributionResult:
    return AttributionResult(
        success=True,
        status=AttributionStatus.UNAVAILABLE,
        identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
        attributed_person_id=None,
        attributed_profile_id=None,
        attributed_artifact_id=None,
        confidence=0.0,
        confidence_band=ConfidenceBand.UNAVAILABLE,
        reason_code=reason_code,
        attribution_method=AttributionMethod.NONE,
        is_confident=False,
        is_ambiguous=False,
        is_abstained=True,
        diagnostic_summary=AttributionDiagnosticSummary(
            diagnostic_available=False,
            diagnostic_reason_code="diagnostics_unavailable",
            repair_available=False,
            health_status="unavailable",
            attribution_readiness="unavailable",
            compatibility_readiness="unavailable",
        ),
        repair_hint_code="review_component_health",
        suggested_next_action_code="reload_voice_identity",
        health_status="unavailable",
        readiness_status="unavailable",
    )


def _persist_runtime_record(
    *,
    runtime: dict[str, object],
    request: AttributionRequest,
    attribution: AttributionResult,
):
    store = _resolve_context_store(runtime)
    now = _utcnow()
    store.sweep_expired(now=now)

    record = build_runtime_attribution_record(
        request=request,
        attribution=attribution,
        now=now,
    )

    existing = store.resolve_current_speaker(
        conversation_id=request.conversation_id,
        device_id=request.device_id,
        satellite_id=request.satellite_id,
        room_id=request.room_id,
        now=now,
    )

    # Supersession and invalid-context handling remain in Voice Identity lifecycle ownership.
    if record.decision.state in {"unknown", "unavailable"}:
        if request.conversation_id:
            store.invalidate_by_conversation(request.conversation_id)
        elif request.device_id or request.satellite_id:
            store.invalidate_by_device_satellite(
                device_id=request.device_id,
                satellite_id=request.satellite_id,
            )
    elif (
        existing is not None
        and existing.subject.person_id
        and record.subject.person_id
        and existing.subject.person_id != record.subject.person_id
    ):
        if request.conversation_id:
            store.invalidate_by_conversation(request.conversation_id)
        elif request.device_id or request.satellite_id:
            store.invalidate_by_device_satellite(
                device_id=request.device_id,
                satellite_id=request.satellite_id,
            )

    persisted = store.upsert(record)
    store.sweep_expired(now=now)
    return store.with_freshness(persisted, age_ms=0, freshness_class=persisted.freshness.freshness_class)


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
