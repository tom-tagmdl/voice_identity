# Attribution

## Service

Use `voice_identity.attribute_speaker` for advisory attribution evidence.

## Advisory Model

Attribution is advisory evidence and not identity truth.

Attribution is performed while audio evidence is available.

Runtime attribution context is then published as short-lived safe context for
text-time consumers.

## Confidence Model

Responses include confidence and confidence bands with deterministic behavior for identical inputs/runtime state.

## Reason Codes

Outputs include machine-safe reason-code taxonomy for ready, abstained, unavailable, and dependency-failure paths.

Safe state taxonomy includes:

- known
- ambiguous
- unknown
- unavailable
- not_required

## Unknown and Abstention

Unknown is valid. Abstention is preferred over unsafe guessing.

## Limits

Attribution outputs remain privacy-safe and do not expose biometric internals or raw payloads.

`conversation_id` is a correlation key for runtime lookup and not a speaker
identity authority.
