# Identity Context

## Service

Use `voice_identity.get_identity_context` for canonical identity context projection.

## Canonical States

- known
- unknown
- low_confidence
- unavailable

## Meaning

Identity Context is behavioral context for downstream decision workflows.

Identity Context is not authentication.

Identity Context is not authorization.

## Safety

Identity context remains fail-closed and privacy-safe under dependency failures.
