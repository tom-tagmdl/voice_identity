# Privacy and Security

## Prohibited Exposure

Voice Identity public surfaces must not expose:

- raw audio
- enrollment recordings
- transcripts
- vectors
- embeddings
- fingerprint vectors
- artifacts
- storage paths
- provider internals
- registry internals
- secrets
- exception traces

## Safe Boundaries

- Services expose safe metadata and reason codes only.
- Diagnostics and telemetry are sanitized.
- Repairs are recommendation-only.
- Fail-closed handling is required for unavailable dependencies.

## Operational Safety

Use diagnostics, repairs, health, and telemetry outputs for support workflows without collecting biometric internals.
