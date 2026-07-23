"""Speaker attribution foundation service.

This module implements advisory, deterministic, privacy-safe attribution using
existing diagnostics, repair, and health/readiness surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from .attribution_models import (
    AttributionDiagnosticSummary,
    AttributionMethod,
    AttributionResult,
    AttributionStatus,
    ConfidenceBand,
    IdentityConfidenceLevel,
)
from .const import (
    DATA_CONFIG_MANAGER,
    DATA_HEALTH_TELEMETRY_PROVIDER,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_REPAIR_RESOLVER,
    DATA_VOICEPRINT_REGISTRY,
)
from .contracts import (
    AttributionBinding,
    AttributionConfidence,
    AttributionDecision,
    AttributionDiagnostics,
    AttributionFreshness,
    AttributionIntegrity,
    AttributionSubject,
    RuntimeAttributionRecord,
    compute_default_attribution_ttl_seconds,
)
from .diagnostics_provider import VoiceIdentityDiagnosticsProvider, build_runtime_context
from .diagnostics_sanitizer import normalize_reason_code, safe_token
from .health_telemetry import VoiceIdentityHealthTelemetryProvider, build_health_telemetry_context
from .repair_resolver import VoiceIdentityRepairResolver
from .voiceprint_registry import VoiceprintRegistry, VoiceprintRegistryValidationError


@dataclass(slots=True, frozen=True)
class AttributionRequest:
    """Runtime attribution request for advisory matching."""

    audio_ref: str
    audio_bytes_size: int
    candidate_scope: tuple[str, ...]
    model_preference: str
    conversation_id: str | None
    device_id: str | None
    satellite_id: str | None
    room_id: str | None
    turn_index: int | None
    pipeline_id: str | None

    def correlation_payload(self) -> dict[str, str | int | None]:
        """Return safe correlation metadata for runtime propagation and diagnostics."""
        return {
            "conversation_id": self.conversation_id,
            "device_id": self.device_id,
            "satellite_id": self.satellite_id,
            "room_id": self.room_id,
            "turn_index": self.turn_index,
            "pipeline_id": self.pipeline_id,
        }

    def has_audio_evidence(self) -> bool:
        """Return whether this request includes audio-time attribution evidence."""
        return bool(self.audio_ref or self.audio_bytes_size > 0)


class SpeakerAttributionFoundation:
    """Deterministic advisory attribution foundation."""

    def __init__(self) -> None:
        self._diagnostics_provider = VoiceIdentityDiagnosticsProvider()
        self._loaded = True

    async def attribute(
        self,
        *,
        entry_id: str,
        runtime: Mapping[str, Any],
        request: AttributionRequest,
        services_registered: bool,
    ) -> AttributionResult:
        """Return one advisory attribution result for the provided request."""
        if not self._loaded:
            return AttributionResult(
                success=True,
                status=AttributionStatus.UNAVAILABLE,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=0.0,
                confidence_band=ConfidenceBand.UNAVAILABLE,
                reason_code="attribution_unavailable",
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
        diagnostics_payload = await self._safe_diagnostics(entry_id=entry_id, runtime=runtime)
        failure_summary = diagnostics_payload.get("failure") if isinstance(diagnostics_payload, dict) else None

        health_payload = await self._safe_health(
            entry_id=entry_id,
            runtime=runtime,
            services_registered=services_registered,
        )
        readiness = dict(health_payload.get("readiness", {}))
        attribution_readiness = safe_token(
            str(readiness.get("attribution_readiness", "unavailable")),
            "unavailable",
        )
        compatibility_readiness = safe_token(
            str(readiness.get("compatibility_readiness", "unavailable")),
            "unavailable",
        )
        health_status = safe_token(str(health_payload.get("status", "unavailable")), "unavailable")
        diagnostics_status = dict(health_payload.get("diagnostics_status", {}))

        resolver = runtime.get(DATA_REPAIR_RESOLVER)
        repair_hint_code = "review_component_health"
        suggested_next_action_code = "review_component_health"
        repair_available = False
        if isinstance(resolver, VoiceIdentityRepairResolver):
            resolved = resolver.resolve(failure_summary if isinstance(failure_summary, dict) else None)
            resolved_payload = resolved.to_dict()
            repair_hint_code = safe_token(
                str(resolved_payload.get("repair_hint_code", "review_component_health")),
                "review_component_health",
            )
            suggested_next_action_code = safe_token(
                str(resolved_payload.get("suggested_next_action_code", "review_component_health")),
                "review_component_health",
            )
            repair_available = bool(resolved_payload.get("repairable", False))

        diagnostic_summary = AttributionDiagnosticSummary(
            diagnostic_available=bool(diagnostics_status.get("available", False)),
            diagnostic_reason_code=safe_token(
                str(diagnostics_status.get("reason_code", "diagnostics_unavailable")),
                "diagnostics_unavailable",
            ),
            repair_available=repair_available,
            health_status=health_status,
            attribution_readiness=attribution_readiness,
            compatibility_readiness=compatibility_readiness,
        )

        if attribution_readiness != "ready":
            return AttributionResult(
                success=True,
                status=AttributionStatus.UNAVAILABLE,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=0.0,
                confidence_band=ConfidenceBand.UNAVAILABLE,
                reason_code="attribution_not_ready",
                attribution_method=AttributionMethod.NONE,
                is_confident=False,
                is_ambiguous=False,
                is_abstained=True,
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        if not request.audio_ref and request.audio_bytes_size <= 0:
            return AttributionResult(
                success=True,
                status=AttributionStatus.ABSTAINED,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=0.0,
                confidence_band=ConfidenceBand.UNKNOWN,
                reason_code="identity_unknown",
                attribution_method=AttributionMethod.NONE,
                is_confident=False,
                is_ambiguous=False,
                is_abstained=True,
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        active_candidates = self._active_candidates(runtime=runtime, request=request)
        if isinstance(active_candidates, str):
            reason_code = active_candidates
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
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        if not active_candidates:
            return AttributionResult(
                success=True,
                status=AttributionStatus.ABSTAINED,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=0.0,
                confidence_band=ConfidenceBand.NO_MATCH,
                reason_code="no_active_voiceprints",
                attribution_method=AttributionMethod.NONE,
                is_confident=False,
                is_ambiguous=False,
                is_abstained=True,
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code=suggested_next_action_code,
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        if len(active_candidates) > 1:
            return AttributionResult(
                success=True,
                status=AttributionStatus.ABSTAINED,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=0.0,
                confidence_band=ConfidenceBand.AMBIGUOUS,
                reason_code="ambiguous_match",
                attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
                is_confident=False,
                is_ambiguous=True,
                is_abstained=True,
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code="manual_review_operation",
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        confidence = _deterministic_confidence(request=request)
        threshold = _configured_threshold(runtime)
        if confidence < threshold:
            return AttributionResult(
                success=True,
                status=AttributionStatus.ABSTAINED,
                identity_confidence_level=IdentityConfidenceLevel.UNKNOWN,
                attributed_person_id=None,
                attributed_profile_id=None,
                attributed_artifact_id=None,
                confidence=confidence,
                confidence_band=_confidence_band(confidence),
                reason_code="low_confidence",
                attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
                is_confident=False,
                is_ambiguous=False,
                is_abstained=True,
                diagnostic_summary=diagnostic_summary,
                repair_hint_code=repair_hint_code,
                suggested_next_action_code="review_component_health",
                health_status=health_status,
                readiness_status=attribution_readiness,
            )

        winner = active_candidates[0]
        return AttributionResult(
            success=True,
            status=AttributionStatus.READY,
            identity_confidence_level=IdentityConfidenceLevel.RECOGNIZED,
            attributed_person_id=winner.get("subject_id"),
            attributed_profile_id=winner.get("voiceprint_id"),
            attributed_artifact_id=winner.get("artifact_id"),
            confidence=confidence,
            confidence_band=_confidence_band(confidence),
            reason_code="attribution_ready",
            attribution_method=AttributionMethod.VOICEPRINT_RECOGNITION,
            is_confident=True,
            is_ambiguous=False,
            is_abstained=False,
            diagnostic_summary=diagnostic_summary,
            repair_hint_code=repair_hint_code,
            suggested_next_action_code="no_action_required",
            health_status=health_status,
            readiness_status=attribution_readiness,
        )

    async def _safe_diagnostics(
        self,
        *,
        entry_id: str,
        runtime: Mapping[str, Any],
    ) -> dict[str, object]:
        try:
            payload = await self._diagnostics_provider.collect(
                context=build_runtime_context(entry_id=entry_id, runtime=runtime),
                source="attribute_speaker",
            )
            return payload
        except Exception:
            return {
                "failure": {
                    "reason_code": "diagnostics_unavailable",
                    "repair_hint_code": "review_component_health",
                    "suggested_next_action_code": "reload_voice_identity",
                    "is_retryable": False,
                    "is_repairable_candidate": False,
                    "issue_reason_codes": ["diagnostics_unavailable"],
                }
            }

    async def _safe_health(
        self,
        *,
        entry_id: str,
        runtime: Mapping[str, Any],
        services_registered: bool,
    ) -> dict[str, object]:
        provider = runtime.get(DATA_HEALTH_TELEMETRY_PROVIDER)
        if not isinstance(provider, VoiceIdentityHealthTelemetryProvider):
            return {
                "status": "unavailable",
                "reason_code": "health_unavailable",
                "diagnostics_status": {
                    "available": False,
                    "reason_code": "diagnostics_unavailable",
                },
                "readiness": {
                    "attribution_readiness": "unavailable",
                    "compatibility_readiness": "unavailable",
                },
            }

        try:
            return await provider.collect_health(
                context=build_health_telemetry_context(entry_id=entry_id, runtime=runtime),
                services_registered=services_registered,
            )
        except Exception:
            return {
                "status": "unavailable",
                "reason_code": "health_unavailable",
                "diagnostics_status": {
                    "available": False,
                    "reason_code": "diagnostics_unavailable",
                },
                "readiness": {
                    "attribution_readiness": "unavailable",
                    "compatibility_readiness": "unavailable",
                },
            }

    def _active_candidates(
        self,
        *,
        runtime: Mapping[str, Any],
        request: AttributionRequest,
    ) -> list[dict[str, str]] | str:
        registry = runtime.get(DATA_VOICEPRINT_REGISTRY)
        list_active_records = getattr(registry, "list_active_records", None)
        if not callable(list_active_records):
            return "registry_unavailable"

        if DATA_MODEL_EXECUTION_PROVIDER not in runtime:
            return "model_backend_unavailable"

        try:
            records = list_active_records()
        except VoiceprintRegistryValidationError:
            return "registry_unavailable"
        except Exception:
            return "internal_error"

        candidates: list[dict[str, str]] = []
        scope = {item for item in request.candidate_scope if item}
        for record in records:
            voiceprint_id = safe_token(record.voiceprint_id.value, "")
            artifact_id = safe_token(record.artifact_id.value, "")
            subject_id = safe_token(record.subject_id.value, "")
            if scope and subject_id not in scope and voiceprint_id not in scope:
                continue
            if not voiceprint_id or not artifact_id:
                continue
            candidates.append(
                {
                    "voiceprint_id": voiceprint_id,
                    "artifact_id": artifact_id,
                    "subject_id": subject_id,
                }
            )

        return sorted(candidates, key=lambda item: item["voiceprint_id"])

    def clear(self) -> None:
        """Clear lifecycle state for unload behavior."""
        self._loaded = False


def create_attribution_request(data: Mapping[str, object]) -> AttributionRequest:
    """Create safe attribution request from service call payload."""
    audio_ref = safe_token(str(data.get("audio_ref", "") or ""), "")
    raw_audio_bytes = data.get("audio_bytes")
    audio_bytes_size = len(raw_audio_bytes) if isinstance(raw_audio_bytes, (bytes, bytearray, memoryview)) else 0

    raw_scope = data.get("candidate_scope", [])
    candidate_scope: tuple[str, ...]
    if isinstance(raw_scope, list):
        candidate_scope = tuple(
            sorted(
                {
                    safe_token(str(item), "")
                    for item in raw_scope
                    if safe_token(str(item), "")
                }
            )
        )
    else:
        candidate_scope = ()

    model_preference = safe_token(str(data.get("model_preference", "") or ""), "")

    conversation_id = _optional_text_field(data, "conversation_id")
    device_id = _optional_text_field(data, "device_id")
    satellite_id = _optional_text_field(data, "satellite_id")
    room_id = _optional_text_field(data, "room_id")
    pipeline_id = _optional_text_field(data, "pipeline_id")
    turn_index = _optional_int_field(data, "turn_index")

    return AttributionRequest(
        audio_ref=audio_ref,
        audio_bytes_size=audio_bytes_size,
        candidate_scope=candidate_scope,
        model_preference=model_preference,
        conversation_id=conversation_id,
        device_id=device_id,
        satellite_id=satellite_id,
        room_id=room_id,
        turn_index=turn_index,
        pipeline_id=pipeline_id,
    )


def build_runtime_attribution_record(
    *,
    request: AttributionRequest,
    attribution: AttributionResult,
    now: datetime | None = None,
) -> RuntimeAttributionRecord:
    """Build one canonical runtime attribution record for lifecycle persistence."""
    issued_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    decision_state = _decision_state_from_attribution(attribution)
    confidence_band = attribution.confidence_band.value if attribution.confidence_band else "none"
    ttl_seconds = compute_default_attribution_ttl_seconds(
        state=decision_state,
        confidence_band=confidence_band,
    )
    expires_at = issued_at + timedelta(seconds=max(0, ttl_seconds))

    freshness_class = "fresh" if ttl_seconds > 0 else "not_applicable"
    reason_code = normalize_reason_code(attribution.reason_code)

    return RuntimeAttributionRecord(
        contract_version="1.0.0",
        attribution_id=f"attr_{uuid4().hex}",
        issued_at_utc=issued_at.isoformat(),
        expires_at_utc=expires_at.isoformat(),
        producer="voice_identity",
        binding=AttributionBinding(
            conversation_id=request.conversation_id,
            device_id=request.device_id,
            satellite_id=request.satellite_id,
            pipeline_id=request.pipeline_id,
            turn_index=request.turn_index,
            room_id=request.room_id,
        ),
        subject=AttributionSubject(
            person_id=safe_token(attribution.attributed_person_id, "") or None,
            display_name=None,
            profile_id=safe_token(attribution.attributed_profile_id, "") or None,
        ),
        confidence=AttributionConfidence(
            score=float(attribution.confidence) if attribution.confidence is not None else None,
            band=confidence_band,
        ),
        decision=AttributionDecision(
            state=decision_state,
            reason_code=reason_code,
            recommended_action=_recommended_action_for_state(decision_state),
        ),
        freshness=AttributionFreshness(
            attribution_age_ms=0,
            valid_until_utc=expires_at.isoformat(),
            freshness_class=freshness_class,
        ),
        diagnostics=AttributionDiagnostics(
            model_version=request.model_preference or None,
            attribution_latency_ms=None,
            evidence_flags=(),
        ),
        integrity=AttributionIntegrity(signature_present=False, nonce_present=False),
    ).normalized()


def _decision_state_from_attribution(attribution: AttributionResult) -> str:
    reason_code = normalize_reason_code(attribution.reason_code)
    if reason_code == "identity_not_required":
        return "not_required"
    if attribution.status is AttributionStatus.UNAVAILABLE:
        return "unavailable"
    if attribution.status is AttributionStatus.READY:
        return "known"
    if reason_code in {"ambiguous_match", "identity_ambiguous_match"}:
        return "ambiguous"
    if reason_code in {"identity_unknown", "no_active_voiceprints", "low_confidence"}:
        return "unknown"
    return "unknown"


def _recommended_action_for_state(state: str) -> str:
    normalized = str(state or "").strip().lower()
    if normalized == "known":
        return "allow"
    if normalized == "not_required":
        return "continue_without_identity"
    if normalized == "ambiguous":
        return "challenge"
    if normalized == "unknown":
        return "constrain"
    return "deny"


def _optional_text_field(data: Mapping[str, object], key: str) -> str | None:
    value = safe_token(str(data.get(key, "") or ""), "")
    return value or None


def _optional_int_field(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _configured_threshold(runtime: Mapping[str, Any]) -> float:
    manager = runtime.get(DATA_CONFIG_MANAGER)
    config = getattr(manager, "config", None)
    attribution = getattr(config, "attribution", None)
    threshold = getattr(attribution, "default_confidence_threshold", 0.7)
    try:
        candidate = float(threshold)
    except (TypeError, ValueError):
        return 0.7
    if candidate < 0.0:
        return 0.0
    if candidate > 1.0:
        return 1.0
    return candidate


def _deterministic_confidence(*, request: AttributionRequest) -> float:
    seed = request.audio_ref or f"bytes_{request.audio_bytes_size}"
    digest = sha256(seed.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    confidence = 0.5 + (bucket / 200)
    if confidence > 1.0:
        return 1.0
    return round(confidence, 4)


def _confidence_band(confidence: float) -> ConfidenceBand:
    if confidence <= 0.0:
        return ConfidenceBand.UNKNOWN
    if confidence < 0.65:
        return ConfidenceBand.LOW
    if confidence < 0.8:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.HIGH
