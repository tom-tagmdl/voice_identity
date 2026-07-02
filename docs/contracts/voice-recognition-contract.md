# Voice Recognition Contract

## Purpose

This contract defines how voice identity is represented and consumed by Concierge.

It establishes shared rules for:

- enrollment
- speaker attribution
- confidence scoring
- fusion with other identity signals
- deletion and revocation

---

## Core Principle

Voice identity is probabilistic context.

It changes how Concierge addresses and prioritizes a person.

It does not change system truth.

---

## Scope

This contract applies to:

- Concierge enrollment flows
- speaker attribution services
- person-aware greeting and style routing
- learning and correction loops

This contract does not define authentication or access control.

---

## Required Inputs

Voice-capable implementations may read:

- person profile reference
- captured voice samples
- enrolled speaker embeddings
- optional speaker-attribution provider output
- active room and interaction space context
- presence and occupancy context
- conversation ownership context

---

## Required Outputs

Voice recognition output must include:

- speaker_candidate or neutral
- confidence
- speaker_embedding_match
- top_candidates
- attribution_factors
- enrollment_state
- expiration metadata
- explainability summary

---

## Decision Rights

Voice recognition may:

- attribute likely speaker identity
- recommend greeting style
- contribute to responder election
- suggest a person profile update after corrections

---

## Non-Rights

Voice recognition must not:

- bypass room context
- bypass safety policy
- directly authorize protected actions
- override lower-layer truth
- create hidden identity behavior

---

## Confidence Rules

Behavior by confidence:

- high confidence: use person name and style
- medium confidence: use cautious personalization
- low confidence: use neutral address and continue deterministically

---

## Enrollment Rules

Enrollment must be:

- explicit
- consent-based
- revocable
- explainable
- auditable

Enrollment must support delete and reset operations.

---

## Learning Rules

The system may learn from:

- repeated successful matches
- explicit user corrections
- enrollment re-runs
- failure analysis

Learning must be reversible and bounded.

---

## Explainability Rules

Voice recognition must produce two forms of explainability.

Machine form:

- confidence values
- reason codes
- candidate list
- timestamps

Human form:

- plain-language summary
- no technical jargon unless requested

---

## Failure Handling

If voice identity data is weak or stale:

- fall back to neutral style
- continue command processing
- preserve deterministic action resolution

The system must not fail the command because voice identity is uncertain.

---

## Integration Responsibilities

### Concierge

Must:

- consume voice identity when available
- fuse it with person and room context
- keep behavior explainable

Must not:

- make voice identity the only deciding factor
- let voice identity override posture or safety rules

### Other Integrations

May:

- expose speaker attribution as a service or event

Must not:

- bypass contract outputs in Concierge

---

## Final Principle

Voice recognition should help Concierge know who is speaking so it can respond in a way that feels natural, respectful, and calm.
