# Identity Governance Reference

## Purpose

This document collects the governance rules that must stay visible as Concierge voice identity and person identity evolve.

It exists to prevent important trust, safety, and lifecycle rules from being lost across architecture, contracts, models, and UI patterns.

---

## Core Principle

Identity must remain local-first, explainable, consent-based, and reversible.

Identity may improve interaction quality, but it must never become hidden surveillance or silent cloud dependency.

---

## Data Residency Matrix

The default is local-only.

| Data / Capability | Default Residency | Cloud Allowed | Notes |
|---|---|---|---|
| Voice samples | Local | Exception only | Capture and processing should remain in-home whenever possible. |
| Speaker embeddings | Local | Exception only | Embeddings are part of identity trust and should not leave the network by default. |
| Voice profiles | Local | Exception only | Profiles should stay in local storage unless a user explicitly opts into an exception. |
| Person profiles | Local | No default cloud path | These are home context records and should remain local. |
| BLE proximity signals | Local | No default cloud path | Used as supporting identity context. |
| Aqara presence signals | Local | No default cloud path | Used as supporting room/context input. |
| Confidence history | Local | Exception only | May be exported only if explicitly consented to for diagnostics. |
| Corrections and learning records | Local | Exception only | Must remain auditable and reversible. |
| Diagnostics payloads | Local | Optional export | Only if the user explicitly enables diagnostics sharing. |

---

## Consent And Revocation Lifecycle

The lifecycle must be explicit and user-visible.

1. Enrollment requested
2. Purpose explained in plain language
3. User grants consent
4. Samples or device links are captured
5. Profile is created or updated
6. Confidence and freshness are stored
7. User may pause, disable, or revoke at any time
8. Revocation immediately stops active use
9. Delete removes the active profile and enrolled data per retention policy
10. Re-enrollment is allowed later

Rules:

- revocation must be immediate
- delete must be explicit
- pause must be reversible
- consent must be scoped to purpose
- no silent enrollment is allowed

---

## Confidence Threshold Policy

Confidence thresholds determine how Concierge may respond.

Suggested operating bands:

- High confidence: may greet by name and apply person style directly
- Medium confidence: may apply cautious personalization and conservative responder election
- Low confidence: use neutral style and preserve deterministic execution
- Very low confidence: request a concise clarification only when necessary

Thresholds must be visible in policy and tunable over time.

Rules:

- thresholds are for delivery and routing, not truth mutation
- thresholds must not override room context or safety policy
- low confidence must never block low-risk deterministic actions

---

## Responder Election Policy

When multiple assistants hear the same request, Concierge must select one primary responder.

Election inputs:

- active interaction space
- room proximity
- likely speaker confidence
- presence context
- conversation ownership
- room posture and activity
- recent successful responder history

Tie-breakers:

1. active conversation owner
2. strongest interaction space confidence
3. strongest likely speaker confidence
4. closest room proximity
5. most recent stable responder in the same conversation

Rules:

- select one primary responder only
- suppress duplicate responses
- preserve conversation continuity
- log the reason code for the chosen responder

---

## Learning And Rollback Policy

Learning is allowed only when it is bounded and reversible.

Learning may adjust:

- person style preferences
- responder weighting
- speaker attribution confidence
- room and person signal weights

Learning must not directly rewrite foundational truth.

Rollback requirements:

- every learned update must be reversible
- every learned update must include a timestamp and trigger
- users must be able to undo or reset learned changes
- stale learned behavior must decay over time

---

## Diagnostics And Explainability Policy

Explainability must be available in both machine and human forms.

Machine form:

- confidence values
- reason codes
- candidate lists
- signal factors
- timestamps
- source lineage

Human form:

- plain-language explanation
- concise reason summary
- no technical jargon unless the user asks for it

Diagnostics should explain:

- why a person was attributed
- why a room or space was selected
- why a responder was elected
- why a cloud exception was used, if any

---

## Voice Training Safety Boundary

Voice training may improve attribution and style, but it must not become hidden authentication.

Rules:

- training is opt-in
- training is revocable
- training is bounded to Concierge-approved use
- training must not bypass safety confirmation rules
- training must not authorize protected actions

---

## Modality And Posture Policy

Response modality must account for room posture and quiet-hours policy.

Examples:

- nighttime posture may suppress spoken replies
- quiet posture may prefer dashboard or visual confirmation
- active daytime posture may allow short spoken responses

Rules:

- posture overrides style verbosity when needed
- response modality must preserve calm behavior
- voice greetings must be suppressed when that reduces disturbance appropriately

---

## Cloud Exception Governance

Cloud use is an exception.

A cloud exception may only occur when:

- the user explicitly opts in
- the purpose is explained
- the local system cannot satisfy the function
- the exception is bounded to the task
- the user can revoke it later

Cloud exceptions must be visible in UI and diagnostics.

Cloud use must never become the hidden default for identity.

---

## Room And Person Setup Separation Rule

The setup experience must keep rooms and people separate at the entry point.

Rules:

- rooms and areas setup is for room/space definitions and device scope
- people setup is for person profiles, device binding, and voice enrollment
- the user must explicitly choose the setup path
- device links for people must be editable from the people path

---

## Terminology Glossary

- Identity Context: the current person-aware context used by Concierge
- Person Profile: the Home Assistant-person-based preference record for style and behavior
- Voice Profile: the enrolled speaker record used for speaker attribution
- Speaker Attribution Snapshot: the runtime match result for a speech event
- Interaction Style Context: the current delivery style chosen for the active person
- Listening Area: the arbitration area used to decide which assistant should respond
- Interaction Space: the active room or merged area where interaction is happening
- Local-first: keep identity and voice data inside the home network by default

---

## Migration And Versioning Note

Identity and voice schemas must be versioned.

Rules:

- schema changes must be backward compatible where practical
- breaking changes must be documented
- profile migrations must be reversible when possible
- legacy voice and person profiles must continue to resolve deterministically until migrated

---

## Final Principle

The most important rules for identity must remain easy to find: local-first, consent-based, explainable, reversible, and calm.
