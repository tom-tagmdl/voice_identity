from dataclasses import asdict

from voice_identity.contracts import (
    FingerprintGenerationRequest,
    FingerprintGenerationResult,
    SpeakerAttributionRequest,
    SpeakerAttributionResult,
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
    request = SpeakerAttributionRequest(audio_ref="audio_1")
    result = SpeakerAttributionResult(matched=False, reason_code="not_implemented")

    assert request.audio_ref == "audio_1"
    assert result.matched is False


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
