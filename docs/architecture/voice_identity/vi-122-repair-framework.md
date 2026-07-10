# VI-122 Repair Framework

## Status

Implemented.

## Scope

VI-122 introduces deterministic, read-only repair recommendation capabilities for
Voice Identity.

This framework recommends repairs.

This framework does not execute repairs.

Included:
- canonical immutable repair definition model
- centralized repair registry
- diagnostics-to-repair resolver
- structured repair recommendation projection
- public read-only service: voice_identity.get_repairs
- fail-closed behavior for unavailable diagnostics/runtime dependencies

Excluded:
- remediation execution
- voiceprint generation/regeneration workflows
- deletion/supersede lifecycle mutation
- registry mutation
- telemetry export
- attribution logic

## Architecture

### Inputs

Repairs consume normalized diagnostics output from VI-121, specifically failure
metadata:
- reason_code
- repair_hint_code
- suggested_next_action_code
- is_retryable
- is_repairable_candidate
- issue_reason_codes

Diagnostics remain authoritative for failure detection.

Repairs consume diagnostics and map findings to guidance.

### Core Components

1. repair_definitions.py
- immutable RepairDefinition model
- severity and category classification
- operator_guidance and validation_guidance text
- supported_reason_codes for deterministic mapping

2. repair_registry.py
- centralized registration and lookup
- deterministic reason-code resolution
- stable snapshot projection for auditing and future tooling

3. repair_resolver.py
- deterministic translation of diagnostics failure summary to repair output
- failure taxonomy projection:
  - repair_available
  - repair_not_available
  - retry_recommended
  - manual_intervention_required
  - unsupported_failure_type
  - diagnostics_unavailable

4. services.py
- read-only service: voice_identity.get_repairs
- service gathers diagnostics, resolves repairs, returns structured payload
- fail-closed fallback on runtime absence or exception

## Determinism

Determinism is enforced by:
- normalized reason-code handling
- sorted reason-code and repair-id indexing
- immutable repair definitions
- pure mapping behavior without state mutation

The same diagnostics inputs produce the same repair output.

## Privacy Boundaries

Repair outputs are operator-safe and machine-readable.

Repairs do not expose:
- raw audio
- embeddings or vectors
- enrollment phrases/transcripts
- storage paths or filesystem structure
- credentials, tokens, secrets
- exception stack traces

Guidance text is descriptive and action-oriented, without internal implementation
path disclosure.

## Repair Lifecycle

1. Diagnostics provider emits normalized failure summary.
2. Repair service requests diagnostics payload.
3. Resolver consumes failure metadata and reason codes.
4. Registry returns matching repair definitions.
5. Resolver projects structured recommendations and taxonomy status.
6. Service returns read-only recommendation response.

No mutation or remediation execution occurs in this lifecycle.

## Operator Workflow

1. Call voice_identity.get_repairs.
2. Review status, repairable/retryable flags, and reason codes.
3. Follow operator_guidance for corrective workflow execution outside VI-122.
4. Validate completion using validation_guidance.
5. Re-run diagnostics/repairs to confirm healthy status.

## Extension Points

Future reason codes can be added by:
- introducing new RepairDefinition entries
- registering definitions in the registry
- reusing existing resolver logic without architecture changes

Future consumers (for example VI-123 and telemetry layers) can consume the same
projection model without creating parallel repair systems.

## Boundary Compliance

VI-122 preserves platform boundaries:
- diagnostics remain in VI-121
- lifecycle operations remain in existing managers/operations
- repair subsystem remains recommendation-only
- no parallel registry/lifecycle/attribution subsystem introduced
