# Identity Context

## Service

Use `voice_identity.get_identity_context` for canonical identity context projection.

## Canonical States

- known
- not_required
- unknown
- low_confidence
- unavailable

## Meaning

Identity Context is behavioral context for downstream decision workflows.

Identity Context is not authentication.

Identity Context is not authorization.

Identity Context is short-lived runtime context and must not be treated as a
long-lived identity session.

`conversation_id`, `device_id`, and `satellite_id` are correlation keys for
runtime lookup and are not proof of speaker identity.

## Safety

Identity context remains fail-closed and privacy-safe under dependency failures.
