# Person Identity Contract

## Purpose

This contract defines how person identity is represented and consumed by Concierge.

It establishes shared rules for:

- person attribution
- interaction style personalization
- enrollment and consent
- correction-based improvement

---

## Core Principle

Identity is behavioral context.

Identity does not redefine truth.

Identity does not bypass safety.

---

## Scope

This contract applies to:

- Concierge runtime orchestration
- person-aware response routing
- person preference projection in UI
- opt-in learning mode for attribution and style

This contract does not define authentication security.

---

## Required Inputs

Identity-capable implementations may read:

- Home Assistant person entities
- BLE room proximity devices
- Aqara room presence devices
- presence and occupancy context
- room and interaction space context
- conversation ownership context
- explicit user corrections
- optional speaker-attribution provider output

Implementations must not assume any source is perfect.

---

## Required Outputs

Identity layer output must include:

- person_id or neutral
- confidence
- attribution_factors
- linked_identity_devices
- linked_presence_devices
- effective_interaction_style
- expiration metadata
- explainability summary

---

## Decision Rights

Identity layer may:

- select an effective person context
- apply person style preferences
- recommend device binding during enrollment
- recommend responder election weighting
- recommend clarification when confidence is low

---

## Non-Rights

Identity layer must not:

- mutate foundational truth
- select execution targets directly
- bypass action safety policy
- produce hidden personalization behavior
- silently link or unlink devices without explicit consent

---

## Confidence Rules

Identity confidence must be explicit.

Behavior by confidence:

- high confidence: apply person style
- medium confidence: apply person style with conservative fallback
- low confidence: apply neutral style and optionally ask concise clarification

Low confidence must never block low-risk deterministic actions.

---

## Enrollment And Consent Rules

Enrollment must be explicit and revocable.

Requirements:

- clear consent prompt
- clear purpose description
- clear delete profile option
- clear update profile option
- clear disable identity personalization option
- clear device binding and unbinding option
- clear voice enrollment and unenrollment option

No enrollment may occur silently.

Device bindings are part of the identity profile and must be editable from the people setup flow.

---

## Correction And Learning Rules

The system may learn from correction signals such as:

- wrong person attribution
- style mismatch feedback
- repeated manual style overrides

Learning must be:

- transparent
- reversible
- explainable
- bounded

Learning must never create surprising behavior shifts.

---

## Explainability Rules

Identity processing must produce two explainability forms.

Machine form:

- structured factors and confidence
- reason codes
- timestamps

Human form:

- plain-language explanation
- concise rationale
- no technical jargon unless user requests technical detail

---

## Failure Handling

If identity data is incomplete or stale:

- fall back to neutral household style
- continue deterministic command processing
- request clarification only when required

The system must not fail command execution only because identity is uncertain.

---

## Integration Responsibilities

### Concierge

Must:

- consume identity context when available
- apply person style within policy bounds
- preserve deterministic action behavior

Must not:

- invent identity without evidence
- use identity to bypass room context

### Other Integrations

May:

- expose identity signals through explicit contracts

Must not:

- bypass identity contract outputs in Concierge

---

## Final Principle

Person-aware interaction should improve comfort and reduce friction while preserving determinism, transparency, and user agency.
