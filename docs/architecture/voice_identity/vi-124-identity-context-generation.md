# VI-124 Identity Context Generation

## Status

Implemented.

## Purpose

VI-124 provides a canonical, Concierge-facing Identity Context projection derived from VI-123 attribution output.

Identity Context is runtime behavior context.

Identity Context is not authentication or authorization.

## Scope

Included:
- stable Identity Context states
- deterministic mapping from VI-123 AttributionResult
- privacy-safe identity context projection service
- fail-closed unavailable projection

Excluded:
- changes to Concierge logic
- model scoring internals
- enrollment lifecycle mutations
- personalization policy changes

## Canonical State Surface

- known
- unknown
- low_confidence
- unavailable

## Mapping Rules

- known:
  - attribution status is attribution_ready
  - identity confidence level is recognized
  - attributed profile id is present
- low_confidence:
  - attribution status is attribution_abstained
  - reason_code is low_confidence or ambiguous_match, or confidence band is low/ambiguous
- unknown:
  - attribution is abstained for non-low-confidence reasons
  - or attribution is ready but no safe profile id is available
- unavailable:
  - attribution status is attribution_unavailable
  - or fail-closed internal handling path

## Service Contract

Service name:
- voice_identity.get_identity_context

Behavior:
- read-only
- deterministic for equivalent runtime/input
- privacy-safe projection only
- fail-closed unavailable responses when runtime/dependencies are unavailable

Output shape:
- state
- person_id (optional)
- voice_profile_id (optional)
- confidence (optional)
- confidence_band (optional)
- reason_code
- source=voice_identity
- generated_at

## Privacy Boundaries

Never exposed:
- raw audio or transcripts
- embeddings/vectors/biometric payloads
- filesystem paths
- stack traces or secret-like content
- subsystem internals outside contract fields

## Dependencies

VI-124 consumes VI-123 attribution outputs and does not duplicate attribution decision logic.
