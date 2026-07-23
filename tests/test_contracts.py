from dataclasses import asdict

from voice_identity.contracts import (
    AttributionBinding,
    AttributionConfidence,
    AttributionDecision,
    AttributionDiagnostics,
    AttributionFreshness,
    AttributionIntegrity,
    AttributionSubject,
    FingerprintGenerationRequest,
    FingerprintGenerationResult,
    IdentityContext,
    RuntimeAttributionRecord,
    RUNTIME_IDENTITY_REASON_CODES,
    SpeakerAttributionRequest,
    SpeakerAttributionResult,
    compute_default_attribution_ttl_seconds,
)


def test_fingerprint_generation_contract_instantiates() -> None:
    request = FingerprintGenerationRequest(
        voice_profile_id="vp_1",
        person_id="person_1",
        sample_refs=["sample_a", "sample_b"],
        expected_sample_count=2,
    )
    result = FingerprintGenerationResult(success=False, failure_code="not_implemented")

    assert request.voice_profile_id == "vp_1"
    assert result.success is False


def test_attribution_contract_instantiates() -> None:
    request = SpeakerAttributionRequest(
        audio_ref="audio_1",
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        turn_index=2,
        pipeline_id="pipe-1",
    )
    result = SpeakerAttributionResult(matched=False, reason_code="not_implemented")

    assert request.audio_ref == "audio_1"
    assert request.conversation_id == "conv-1"
    assert request.device_id == "dev-1"
    assert request.satellite_id == "sat-1"
    assert request.room_id == "room-1"
    assert request.turn_index == 2
    assert request.pipeline_id == "pipe-1"
    assert result.matched is False


def test_attribution_contract_allows_legacy_request_without_correlation_keys() -> None:
    request = SpeakerAttributionRequest(audio_ref="audio_1")

    assert request.conversation_id is None
    assert request.device_id is None
    assert request.satellite_id is None
    assert request.room_id is None
    assert request.turn_index is None
    assert request.pipeline_id is None


def test_generation_result_has_safe_fields_and_no_raw_vector_default() -> None:
    result = FingerprintGenerationResult(success=False)
    payload = asdict(result)

    assert "failure_message_safe" in payload
    assert "fingerprint_ref" in payload
    assert "vector" not in payload
    assert "embedding" not in payload


def test_attribution_result_has_safe_fields_and_no_raw_vector_default() -> None:
    result = SpeakerAttributionResult(matched=False)
    payload = asdict(result)

    assert "reason_code" in payload
    assert "failure_message_safe" in payload
    assert "vector" not in payload
    assert "embedding" not in payload


def test_identity_context_contract_has_safe_fields() -> None:
    context = IdentityContext(
        state="unknown",
        person_id=None,
        voice_profile_id=None,
        confidence=None,
        confidence_band=None,
        reason_code="identity_unknown",
    )
    payload = asdict(context)

    assert payload["state"] == "unknown"
    assert payload["source"] == "voice_identity"
    assert "vector" not in payload
    assert "embedding" not in payload


def test_runtime_attribution_record_contract_has_required_safe_sections() -> None:
    record = RuntimeAttributionRecord(
        contract_version="1.0.0",
        attribution_id="attr-1",
        issued_at_utc="2026-07-23T10:00:00+00:00",
        expires_at_utc="2026-07-23T10:00:30+00:00",
        producer="voice_identity",
        binding=AttributionBinding(
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            pipeline_id=None,
            turn_index=1,
            room_id="living_room",
        ),
        subject=AttributionSubject(
            person_id="person_1",
            display_name="Tom",
            profile_id="vp_1",
        ),
        confidence=AttributionConfidence(score=0.93, band="high"),
        decision=AttributionDecision(
            state="known",
            reason_code="identity_known_high_confidence",
            recommended_action="allow",
        ),
        freshness=AttributionFreshness(
            attribution_age_ms=250,
            valid_until_utc="2026-07-23T10:00:30+00:00",
            freshness_class="fresh",
        ),
        diagnostics=AttributionDiagnostics(
            model_version="ecapa_v1",
            attribution_latency_ms=42,
            evidence_flags=("wake_word_present",),
        ),
        integrity=AttributionIntegrity(signature_present=True, nonce_present=True),
    )
    payload = asdict(record)
    rendered = str(payload).lower()

    assert payload["binding"]["conversation_id"] == "conv-1"
    assert payload["decision"]["state"] == "known"
    assert payload["freshness"]["freshness_class"] == "fresh"
    for forbidden in {"audio_bytes", "audio_ref", "embedding", "vector", "biometric"}:
        assert forbidden not in rendered


def test_runtime_ttl_defaults_follow_short_lived_policy() -> None:
    assert compute_default_attribution_ttl_seconds(state="known", confidence_band="high") == 30
    assert compute_default_attribution_ttl_seconds(state="known", confidence_band="medium") == 15
    assert compute_default_attribution_ttl_seconds(state="ambiguous", confidence_band="low") == 5
    assert compute_default_attribution_ttl_seconds(state="unknown", confidence_band="none") == 0
    assert compute_default_attribution_ttl_seconds(state="unavailable", confidence_band="none") == 0
    assert compute_default_attribution_ttl_seconds(state="not_required", confidence_band="none") == 10


def test_runtime_reason_code_catalog_includes_required_safe_codes() -> None:
    required = {
        "identity_known_high_confidence",
        "identity_known_medium_confidence",
        "identity_known_low_confidence",
        "identity_ambiguous_match",
        "identity_unknown",
        "identity_unavailable",
        "identity_audio_missing",
        "identity_context_missing",
        "identity_context_stale",
        "identity_context_expired",
        "identity_not_required",
        "identity_required_but_missing",
        "identity_required_fresh_but_stale",
        "identity_policy_blocked_sensitive_intent",
        "identity_step_up_required",
    }
    assert required.issubset(set(RUNTIME_IDENTITY_REASON_CODES))
