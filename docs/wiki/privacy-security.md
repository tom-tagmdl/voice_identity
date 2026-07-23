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
- Runtime attribution context is short-lived and bounded.
- Correlation keys are not identity authority.

## Operational Safety

Use diagnostics, repairs, health, and telemetry outputs for support workflows without collecting biometric internals.

Runtime attribution context should not become a long-lived identity session and
should follow short default TTL windows.
