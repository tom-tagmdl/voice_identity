# Diagnostics

## Service

Use `voice_identity.get_diagnostics` for safe diagnostics projection.

## Reason Codes

Diagnostics emit machine-safe reason-code surfaces, including healthy/degraded/unavailable categories and deterministic hint mappings.

## Safe Projections

Diagnostics are sanitized and sectioned. Unsafe keys and leak-prone values are removed or normalized.

## Fail-Closed Behavior

When runtime is unavailable or an internal exception occurs, diagnostics return fail-closed safe responses with deterministic reason codes.
