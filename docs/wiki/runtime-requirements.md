# Runtime Requirements

## Purpose

This page explains what must be true at runtime for Voice Identity to reliably identify a speaker during normal Home Assistant voice use.

Speaker identity is a production concern solved at speech-to-text ingress, where live audio exists. It cannot be solved later at transcript-only conversation layers.

## Why Downstream-Only Identity Fails

By the time conversation/intent automation runs, raw utterance audio is gone. Only text and metadata remain.

Speaker identification requires audio evidence. If attribution is attempted only at conversation or automation layers, the result will trend to unknown.

## Runtime Model: Production and Consumption

Voice Identity requires two cooperating halves.

### Production (audio-time)

1. Capture live utterance audio at STT ingress.
2. Generate runtime embedding from captured audio.
3. Compare against enrolled voiceprints.
4. Write a short-lived attribution result to context storage.

### Consumption (text-time)

1. Resolve attribution by correlation keys.
2. Apply freshness and authorization policies.
3. Return privacy-safe, explainable outcomes.

If production is absent, consumption has nothing authoritative to consume.

## Required Integration: Forking STT Proxy

The active Assist pipeline must call a Voice Identity STT proxy entity.

The proxy must tee audio concurrently:

- branch A forwards to the real STT backend and preserves transcript behavior
- branch B stays in memory for embedding and comparison

Operational requirements:

- Voice Identity STT proxy is the STT engine configured in the active Assist pipeline.
- Transcript path remains first-class and resilient.
- Identity path is best-effort and never blocks core voice control.

## Correlation Requirements

STT audio callbacks provide bytes and format metadata, but often not full request identity keys.

Required join strategy:

- Primary: context propagation from pipeline run-start into STT processing.
- Fallback: device plus short recency-window correlation.
- Never: infer identity binding from format metadata alone.

Without this join, records may be produced but not discoverable by consumers.

## Enrollment and Runtime Parity

Enrollment and runtime must share one canonical audio and encoder contract.

- sample rate: 16000 Hz
- channels: mono
- sample width: 16-bit PCM
- preprocessing: identical normalization and VAD/window behavior
- encoder: same family and pinned version

Version or preprocessing drift causes unstable confidence and misclassification.

## Performance and Reliability SLO

Runtime attribution must be parallel and bounded.

- target: 800 ms
- p95: 1500 ms
- hard timeout: 1200 ms, then safe fallback to unknown

Required behavior:

- no runtime file I/O on critical attribution path
- no per-request model cold start
- deterministic fail-fast to unknown on backend slowdown/outage
- assistant remains available even when attribution is degraded

## Two-Stage Runtime Decisioning

- Stage 1: fast provisional decision from early voiced audio.
- Stage 2: refined decision from full utterance in background.

Stage 1 supports low-latency experiences. Stage 2 improves confidence and consistency.

## Risk-Tiered Authorization

- Low risk: allow execution if identity unresolved.
- Medium risk: bounded wait for attribution, then constrained behavior.
- High risk: require known and fresh identity; otherwise fail closed or challenge.

## Privacy and Data Boundaries

- Raw audio is in-memory only and released immediately after attribution completes.
- Raw audio, embeddings, vectors, and voiceprints do not cross Voice Identity boundaries.
- Downstream surfaces receive safe attribution projection only:
  - state: known, unknown, ambiguous, unavailable, not_required
  - confidence band
  - matched person reference (when known)
  - freshness
  - safe reason code

## Runtime Readiness Checklist

- [ ] STT proxy is configured and active in the Assist pipeline.
- [ ] STT forwarding path is transcript-parity validated.
- [ ] Correlation join is implemented (primary + fallback).
- [ ] Enrollment/runtime contract parity is enforced.
- [ ] Encoder family/version pinning is enforced.
- [ ] Embeddings/index remain memory-resident at runtime.
- [ ] Attribution executes in parallel with STT.
- [ ] Timeout fail-fast to unknown is enforced.
- [ ] No biometric artifacts are persisted or exposed.
- [ ] High-risk actions fail closed on unknown/ambiguous/stale identity.
- [ ] Stage-level timings and unknown/timeout rates are instrumented.

## Related Pages

- [Attribution](attribution.md)
- [Identity Context](identity-context.md)
- [Privacy and Security](privacy-security.md)
- [Setup](setup.md)
- [Troubleshooting](troubleshooting.md)
