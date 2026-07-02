# Person Identity And Enrollment Architecture

## Purpose

This document defines the architecture for person-aware interaction in Concierge.

It establishes how the system:

- determines who is speaking
- applies person-specific interaction style
- supports explicit opt-in enrollment
- improves attribution and style over time

This architecture is a sub-project of Concierge and must remain aligned with Homes That Behave Well principles.

Voice identity and person identity are local-first by default and governed by the voice identity trust and data residency policy.

---

## Core Principle

Identity changes interaction style, not system truth.

Person awareness may change how Concierge responds.

Person awareness must not change foundational truth, safety boundaries, or deterministic execution rules.

---

## Why This Sub-Project Exists

Current Home Assistant voice architecture is strong at phrase capture and routing.

It is limited in native person attribution.

Concierge requires person-aware context to reduce friction and increase natural interaction quality.

Goals:

- fewer repetitive clarifications
- person-appropriate communication style
- reduced multi-assistant confusion
- improved trust through predictable behavior

---

## Sub-Project Definition

Person Identity And Enrollment is a formal Concierge sub-project with dedicated architecture, contract, model, and pattern governance.

Workstreams:

- identity signal fusion and confidence modeling
- person profile and interaction style modeling
- people setup and people tiles UI
- opt-in learning mode and consent lifecycle
- multi-assistant responder election improvements

Sub-project outputs must be auditable and aligned with Homes That Behave Well principles.

---

## Relationship To Existing Work

Current implementation track is room-first:

- define rooms
- define merged spaces
- define controllable device scope

Person identity architecture builds on that foundation.

Room and space context remains the primary scoping mechanism.

Person context enriches delivery and arbitration.

---

## Layer Placement

The context hierarchy for person-aware interaction is:

Foundation
  -> Room Context
  -> Identity Context
  -> Conversation Context
  -> Interaction Style Context
  -> Activity Context
  -> Attention Context
  -> Intent Resolution
  -> Learning And Adaptation

---

## Architectural Components

### Identity Sources

Identity is derived from multiple bounded sources:

- Home Assistant person entities
- room-level presence context
- BLE room proximity devices
- Aqara room presence devices
- wake-word event locality
- optional speaker-attribution provider
- active conversation ownership history

No single source is authoritative by itself.

Identity is confidence-scored and explainable.

---

### Speaker Attribution

Speaker attribution produces:

- person candidate
- confidence
- attribution factors

Speaker attribution is a context signal.

It is not an authentication boundary.

Low-confidence attribution must degrade to neutral interaction style.

---

### Interaction Style Context

Interaction style context translates person preference into delivery behavior.

Examples:

- direct and concise responses
- conversational and detailed responses
- low follow-up prompts
- richer explanatory prompts

Style application must remain deterministic and bounded by posture and safety policy.

---

### Enrollment And Learning Mode

Enrollment is explicit and opt-in.

The system must support a guided learning mode for household members.

Learning mode should capture:

- person confirmation
- optional voice profile samples
- phrase preference examples
- communication style choices
- BLE proximity device links
- Aqara presence device links

Device links are part of person setup and must be selected explicitly.

Device link types:

- identity devices: BLE proximity sources tied to a person profile
- supporting presence devices: room presence sensors used as contextual signals for a person's usual spaces

Learning mode must include plain-language consent and revocation.

---

## People Setup And Device Binding

People setup must treat device binding as part of the setup flow.

Required setup elements:

- select a Home Assistant person entity
- optionally enroll voice identity
- link BLE proximity devices such as iPhone and watch sources
- link Aqara room presence devices used as supporting context
- save person preference profile

Rules:

- identity devices belong to the person's attribution profile
- supporting presence devices strengthen room and occupancy confidence for that person
- linked devices must be editable and removable later
- device binding must be explainable in the UI

---

## Listening Areas And Multi-Assistant Arbitration

When multiple assistants hear the same wake event, Concierge must elect one primary responder.

Arbitration should evaluate:

- interaction space confidence
- known person presence near responder candidates
- active conversation owner
- room posture and activity
- recent successful responder history

Arbitration must:

- pick one responder
- suppress duplicates
- preserve conversation ownership stability
- log explainable reason codes

---

## Hybrid Freshness Policy

Person-aware context uses hybrid freshness.

Primary:

- event-driven updates for meaningful context changes

Secondary:

- TTL safeguards for stale identity and style state

Freshness tuning must reduce interaction noise and avoid over-churn.

---

## Privacy And Trust Requirements

Person identity capability must be privacy-forward.

By default, the system should keep person identity data and learning inside the home network.

Requirements:

- explicit opt-in enrollment
- explicit opt-out and deletion paths
- explainable purpose of collected data
- least-data retention policy
- bounded data usage for Concierge only

Any voice sample handling must be transparent and revocable.

---

## Execution Rules

Person identity must not change execution correctness.

Rules:

- resolve actionable targets using room and space scope first
- apply person context to routing and response style
- enforce safety policy independent of person style preference
- require confirmation for high-risk actions

---

## Delivery Phases

### Phase 1: Foundation Complete

- room and merged space modeling
- controllable device scoping
- deterministic local-first resolution

### Phase 2: People Configuration UI

- people tiles alongside room tiles
- setup path selection for Rooms And Areas or People
- person style preference editing
- person-to-room interaction insights

### Phase 3: Opt-In Voice Learning Mode

- guided enrollment
- speaker attribution confidence model
- correction-driven tuning

### Phase 4: Progressive Adaptation

- bounded learning from corrections
- explainability-first adaptation records
- reversible preference changes

---

## Success Criteria

- users can issue relaxed commands with less friction
- only one assistant responds per interaction
- interaction style matches person preference with clear override path
- system remains calm, deterministic, and explainable
- behavior improves over time without surprises

---

## Final Principle

Concierge should know where interaction is happening and who interaction is happening with before deciding how to respond.

Person awareness should make the home feel more attentive without making it less predictable.

See also: [identity-governance-reference.md](identity-governance-reference.md)
