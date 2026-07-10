# VI-121 Diagnostics Provider

## Status

Implemented.

## Goal

Provide safe diagnostics surfaces for Voice Identity without exposing raw audio,
embeddings, transcripts, storage paths, secrets, exception text, or stack traces.

## Scope

Included:
- provider-backed diagnostics payload for config-entry diagnostics
- service surface: voice_identity.get_diagnostics
- deterministic sectioned diagnostics projection
- sanitizer policy for nested payloads and reason-code normalization
- repair-ready hint codes (diagnostics only, no repair execution)

Excluded:
- runtime repair actions
- feature expansion outside diagnostics surfaces
- raw internal payload exposure

## Architecture

Diagnostics are assembled by VoiceIdentityDiagnosticsProvider from runtime data
already owned by Voice Identity:
- health engine snapshot
- capability registry snapshot
- configuration manager read-only config
- runtime presence checks for generation/status operations and registry managers

The provider returns fixed sections:
- platform
- model
- enrollment
- generation
- registry
- capability
- failure

## Sanitization Policy

The diagnostics_sanitizer module enforces allowlist-oriented projection:
- only machine-safe keys matching ^[a-z0-9_]+$
- drop keys containing prohibited fragments (audio, embedding, vector,
  transcript, payload, path, token, secret, password, key, trace, exception)
- normalize reason codes to ^[a-z0-9_]+$ or unknown_reason
- redact unsafe free text (traceback/secret/path-like content)
- keep only primitive-safe values and sanitized nested mappings/lists

This policy is applied to all diagnostics sections before returning payloads.

## Service Contract

Service name: voice_identity.get_diagnostics

Input:
- optional entry_id

Behavior:
- resolves runtime by entry_id when provided
- otherwise resolves deterministic first runtime entry
- fail-closed on missing runtime with reason_code=runtime_unavailable

Output:
- success (bool)
- reason_code
- entry_id
- diagnostics (safe sectioned payload)

## Failure Taxonomy and Hint Codes

Failure section includes:
- issue_reason_codes: normalized reasons from unhealthy components
- repair_hint_codes: machine-safe hints mapped from known reason codes

Examples:
- model_provider_unavailable -> verify_model_backend
- voiceprint_artifact_missing -> run_registry_reconciliation
- configuration_invalid -> verify_configuration
- unrecognized/unsafe reason -> unknown_reason with review_component_health

## Determinism

Diagnostics payload is deterministic:
- fixed top-level sections
- sorted reason code sets
- sorted hint code sets
- sanitized/sorted mapping keys
- no timestamp fields in provider output

## Forward Readiness

VI-121 surfaces are designed to unblock downstream work:
- VI-122 can consume failure hint codes for guided checks
- VI-123 can consume deterministic section contracts for UI diagnostics cards
- VI-125 can layer structured telemetry on top of the same safe section model

All downstream usage should preserve the same no-leak boundaries.
