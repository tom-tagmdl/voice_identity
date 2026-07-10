# VI-123 Speaker Attribution Foundation

## Status

Implemented.

## Dependency Gate

VI-123 consumes completed foundations:
- VI-121 Diagnostics Provider
- VI-122 Repair Framework
- VI-125 Health and Telemetry Integration

Consumed surfaces include:
- get_health and get_telemetry runtime projections
- attribution_readiness and compatibility_readiness
- diagnostics failure summary projection
- repair hint and next-action projection

## Purpose

VI-123 establishes advisory, deterministic, privacy-safe attribution contracts
for runtime speaker evidence.

Speaker attribution provides evidence.

Speaker attribution does not declare identity truth.

Unknown is a valid attribution result.

Attribution abstention is preferred over unsafe guessing.

## Scope

Included:
- attribution request and result models
- identity confidence level surface
- confidence band surface
- reason-code taxonomy for unavailable/abstained/recognized outcomes
- read-only attribute_speaker service
- diagnostics, repairs, and health/readiness consumption

Excluded:
- identity context generation (VI-124)
- Concierge context fusion
- enrollment or voiceprint lifecycle mutation
- repair execution
- telemetry export
- personalization and behavior changes

## Identity Confidence Levels

VI-123 supports the canonical identity-confidence model:
- unknown
- asserted
- inferred
- recognized

Current implementation produces recognized and unknown outcomes for
voiceprint-based advisory matching while preserving compatibility with future
asserted and inferred evidence sources.

## Confidence Model

Confidence is deterministic and bounded.

A placeholder deterministic confidence scorer is used for foundation behavior,
with contract-safe bands:
- unavailable
- unknown
- no_match
- low
- medium
- high
- ambiguous

Threshold governance remains owned by configuration and future model/scoring
workflows.

## Reason-Code Surface

VI-123 emits machine-safe reason codes including:
- attribution_ready
- attribution_unavailable
- attribution_abstained
- attribution_not_ready
- identity_unknown
- no_active_voiceprints
- ambiguous_match
- low_confidence
- model_backend_unavailable
- registry_unavailable
- diagnostics_unavailable
- health_unavailable
- internal_error

## Service Contract

Service name:
- voice_identity.attribute_speaker

Behavior:
- read-only
- fail-closed
- advisory only
- deterministic for identical input and runtime state
- privacy-safe structured response

## Integration Boundaries

Diagnostics remain authoritative for diagnostics detail.

Repairs remain authoritative for repair guidance.

Health/readiness remains authoritative from VI-125.

VI-123 consumes these surfaces and does not duplicate subsystem logic.

## Privacy Boundaries

Never exposed:
- raw audio or transcripts
- vectors/embeddings/biometric payloads
- filesystem paths
- registry internals not approved for public contracts
- raw exception traces or secret-like content

Only safe identifiers and contract-approved metadata are returned.

## Fail-Closed Behavior

When dependencies are unavailable or attribution readiness is not ready,
VI-123 returns structured unavailable/abstained outputs with deterministic
reason codes and safe next-action hints.

No mutation or remediation actions are executed.

## VI-124 Readiness

VI-123 provides a stable advisory attribution projection that VI-124 can
consume without accessing internal model/runtime implementation details.
