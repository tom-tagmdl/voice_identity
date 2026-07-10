# VI-125 Health and Telemetry Integration

## Status

Implemented.

## Purpose

VI-125 integrates health and telemetry projection across Voice Identity runtime
components while preserving established subsystem authority.

Health reflects real component state.

Telemetry is privacy-safe operational projection.

Telemetry is not external export.

## Dependency Gate

VI-125 consumes:
- VI-103 Health State Engine (authoritative health-state evaluation)
- VI-121 Diagnostics Provider (authoritative diagnostics projection)

Both dependencies are present and consumed through public runtime/provider
surfaces.

## Scope

Included:
- runtime health aggregation provider over existing health, diagnostics, repair,
  and capability surfaces
- privacy-safe telemetry projection for operational visibility
- read-only service surfaces: voice_identity.get_health and
  voice_identity.get_telemetry
- readiness projections for attribution (VI-123) and compatibility/migration
  diagnostics (VI-126)
- fail-closed behavior and deterministic reason-code outputs

Excluded:
- health engine replacement or alternate health-state logic
- diagnostics generation replacement
- repair recommendation replacement
- external telemetry export or analytics
- any mutation/remediation behavior

## Architecture Relationships

### VI-103 (Health)

VI-103 remains authoritative for component health-state calculation and state
taxonomy.

VI-125 reads health snapshots and projects aggregate status.

### VI-121 (Diagnostics)

VI-121 remains authoritative for diagnostics detail and failure projection.

VI-125 consumes diagnostics availability/failure summary through safe provider
outputs and does not expose raw diagnostics internals.

### VI-122 (Repairs)

VI-122 remains authoritative for repair recommendation logic.

VI-125 consumes repair readiness/hints and does not execute repairs.

## Service Contracts

### voice_identity.get_health

Read-only deterministic response including:
- status and reason_code
- health booleans (healthy/degraded/available/recoverable)
- diagnostics and repairs availability
- component status projection
- attribution and compatibility readiness

### voice_identity.get_telemetry

Read-only privacy-safe response including:
- telemetry status and reason_code
- component_status summary
- service_status summary
- capability_status summary
- diagnostics/repair readiness summary
- compatibility and attribution readiness

## Privacy Boundaries

VI-125 projections are sanitized using the same policy discipline as VI-121.

Not exposed:
- raw audio
- embeddings/vectors
- transcripts
- artifact payloads
- filesystem paths
- secrets/tokens/credentials
- raw exceptions/stack traces

## Failure Taxonomy

VI-125 surfaces deterministic reason codes and fail-closed outputs for missing
runtime/dependencies, including unavailable/degraded paths and safe next-action
hints.

## Readiness Outputs

VI-125 exposes:
- attribution_readiness for VI-123 dependency consumption
- compatibility_readiness for VI-126 dependency consumption

Readiness is derived from real component health states (ready/degraded/
unavailable) and not static placeholders.

## Runtime Lifecycle

Health/telemetry provider is:
- instantiated during setup
- stored in runtime data
- cleared during unload

Service registration follows existing domain service lifecycle patterns and is
cleanly removed during unload.

## Boundary Assertions

Diagnostics remain authoritative for diagnostics detail.

Repairs remain authoritative for repair recommendations.

Health and telemetry do not expose biometric material.

Health and telemetry do not execute actions.
