# Health and Telemetry

## Services

- `voice_identity.get_health`
- `voice_identity.get_telemetry`

## Readiness Surfaces

Health and telemetry expose deterministic readiness fields:

- `attribution_readiness`
- `compatibility_readiness`

Allowed readiness states are ready/degraded/unavailable projections.

## Operational Semantics

- Health reflects current required/optional component state.
- Telemetry is a privacy-safe operational projection for support workflows.
- Fail-closed behavior is required when dependencies are unavailable.

## No External Export

Telemetry in this repository is not an external export pipeline.
