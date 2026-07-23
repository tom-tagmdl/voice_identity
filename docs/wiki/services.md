# Services

Services are defined in custom_components/voice_identity/services.yaml and implemented as read-only, fail-closed runtime projections.

## voice_identity.get_diagnostics

- Purpose: return safe diagnostics projection.
- Input: optional `entry_id`.
- Output: success, reason_code, entry_id, diagnostics payload.
- Privacy notes: sanitized payload only.

## voice_identity.get_repairs

- Purpose: return deterministic repair recommendations.
- Input: optional `entry_id`.
- Output: success, reason_code, entry_id, repairs payload.
- Privacy notes: recommendation-only guidance, no execution.

## voice_identity.get_health

- Purpose: return runtime health aggregation.
- Input: optional `entry_id`.
- Output: success, reason_code, entry_id, health payload.
- Privacy notes: operational projection only.

## voice_identity.get_telemetry

- Purpose: return privacy-safe telemetry projection.
- Input: optional `entry_id`.
- Output: success, reason_code, entry_id, telemetry payload.
- Privacy notes: no external telemetry export.

## voice_identity.attribute_speaker

- Purpose: return advisory attribution evidence.
- Input: optional `entry_id`, `audio_ref`, `candidate_scope`, `model_preference`.
- Output: success, reason_code, entry_id, attribution payload.
- Privacy notes: no raw audio, vectors, or traces.

## voice_identity.get_identity_context

- Purpose: return canonical identity context projection.
- Input: optional `entry_id`, `audio_ref`, `candidate_scope`, `model_preference`.
- Output: success, reason_code, entry_id, identity_context payload.
- Privacy notes: behavioral context only.

## Runtime Attribution Context Store (Internal Contract)

Voice Identity owns the runtime attribution context store used to bridge
audio-time attribution and text-time conversation execution.

Conceptual interface:

- `upsert(record)`
- `resolve_current_speaker(conversation_id, device_id, satellite_id, room_id, now)`
- `invalidate_by_conversation(conversation_id)`
- `invalidate_by_device_satellite(device_id, satellite_id)`
- `sweep_expired(now)`

This store is short-lived by design. It is not exposed as a raw payload surface.
