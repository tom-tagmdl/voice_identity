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
- conversation_id (optional)
- device_id (optional)
- satellite_id (optional)
- room_id (optional)
- turn_index (optional)
- pipeline_id (optional)
- requested_at

Correlation key purpose:

- lookup
- routing
- freshness
- speaker handoff
- store resolution

Correlation key non-purpose:

- identity proof
- speaker ownership
- authorization
- biometric evidence

Example request payload (legacy-compatible):

```yaml
audio_ref: session_audio_ref_001
candidate_scope:
	- person_001
model_preference: ecapa_v1
conversation_id: conv_20260723_001
device_id: assist_satellite_kitchen
satellite_id: sat_kitchen_01
room_id: kitchen
turn_index: 3
pipeline_id: assist_pipeline_primary
```

Example legacy payload (still valid):

```yaml
audio_ref: session_audio_ref_001
candidate_scope:
	- person_001
model_preference: ecapa_v1
```

## SpeakerAttributionResult

Fields:

- matched
- person_id
- voice_profile_id
- speaker_match_confidence
- threshold
- reason_code
- failure_message_safe

## RuntimeAttributionRecord

Fields:

- contract_version
- attribution_id
- issued_at_utc
- expires_at_utc
- producer
- binding
	- conversation_id
	- device_id
	- satellite_id
	- pipeline_id
	- turn_index
	- room_id
- subject
	- person_id
	- display_name
	- profile_id
- confidence
	- score
	- band (`high|medium|low|none`)
- decision
	- state (`known|ambiguous|unknown|unavailable|not_required`)
	- reason_code
	- recommended_action (`allow|challenge|deny|constrain|continue_without_identity`)
- freshness
	- attribution_age_ms
	- valid_until_utc
	- freshness_class (`fresh|stale|expired|not_applicable`)
- diagnostics
	- model_version
	- attribution_latency_ms
	- evidence_flags
- integrity
	- signature_present
	- nonce_present

Runtime attribution records are short-lived bridge records for audio-time to
text-time correlation. They are not long-lived identity sessions.

Default TTL policy:

- known high confidence: 30 seconds
- known medium confidence: 15 seconds
- low confidence or ambiguous: 5 to 10 seconds
- unknown: no reuse
- unavailable: no reuse

Absolute max cap: 60 seconds unless superseded by accepted ADR authority.

## Attribution Context Store Interface

Voice Identity owns the runtime attribution context store and lifecycle.

Conceptual methods:

- `upsert(record)`
- `resolve_current_speaker(conversation_id, device_id, satellite_id, room_id, now)`
- `invalidate_by_conversation(conversation_id)`
- `invalidate_by_device_satellite(device_id, satellite_id)`
- `sweep_expired(now)`

`conversation_id` is a correlation key and not identity authority.

## Runtime Lifecycle Ownership

Voice Identity owns:

- runtime attribution records
- store lifecycle and expiry
- freshness and stale/expired semantics
- supersession and handoff-safe replacement

Concierge does not own:

- attribution truth
- biometric internals
- attribution context lifecycle storage

## Freshness Model

- `fresh`: record is valid and not near expiry
- `stale`: record is valid but near expiry and should be treated conservatively
- `expired`: record is invalid and cannot resolve current speaker
- `not_applicable`: no-reuse record class (for example unknown/unavailable)

## Invalidation Strategy

Voice Identity may invalidate records by:

- `conversation_id` scope when correlation context is invalidated
- `device_id` + `satellite_id` scope when device-bound context is invalidated

Unknown or unavailable attribution outcomes are no-reuse outcomes and must not
remain identity-authoritative for future speaker resolution.

## Privacy Rules

Never expose:

- raw audio
- fingerprint vectors
- storage paths
- provider IDs
- embeddings
- biometric internals
- raw attribution store internals
- person-sensitive internals beyond required IDs

## Compatibility and Migration Validation

Contract and schema compatibility behavior, migration-required validation, and
supported/unsupported path coverage are defined by VI-126 matrix tests and
documentation:

- docs/architecture/voice_identity/vi-126-compatibility-and-migration-test-matrix.md
