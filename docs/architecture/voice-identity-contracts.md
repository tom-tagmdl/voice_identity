# Voice Identity Contracts

## FingerprintGenerationRequest

Fields:

- voice_profile_id
- person_id
- sample_refs
- expected_sample_count
- model_preference
- requested_at

## FingerprintGenerationResult

Fields:

- success
- fingerprint_ref
- fingerprint_schema_version
- fingerprint_model
- fingerprint_model_version
- fingerprint_dimension
- fingerprint_quality_score
- fingerprint_sample_count
- failure_code
- failure_message_safe

## SpeakerAttributionRequest

Fields:

- audio_ref or audio_bytes
- candidate_scope
- model_preference
- requested_at

## SpeakerAttributionResult

Fields:

- matched
- person_id
- voice_profile_id
- speaker_match_confidence
- threshold
- reason_code
- failure_message_safe

## Privacy Rules

Never expose:

- raw audio
- fingerprint vectors
- storage paths
- provider IDs
- embeddings
- biometric internals
- person-sensitive internals beyond required IDs

## Compatibility and Migration Validation

Contract and schema compatibility behavior, migration-required validation, and
supported/unsupported path coverage are defined by VI-126 matrix tests and
documentation:

- docs/architecture/voice_identity/vi-126-compatibility-and-migration-test-matrix.md
