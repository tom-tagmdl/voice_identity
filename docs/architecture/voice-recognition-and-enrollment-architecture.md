# Voice Recognition And Enrollment Architecture

## Purpose

This document defines how Concierge should learn and use user voice identity.

It establishes the architecture for:

- voice enrollment
- speaker attribution
- confidence-based matching
- opt-in learning mode
- interaction style adaptation based on likely speaker

This is a Concierge sub-project and must remain aligned with Homes That Behave Well principles.

Local-first handling is the default and is governed by the voice identity trust and data residency policy.

---

## Core Principle

Voice identity is a confidence-scored context signal.

It may improve who Concierge thinks is speaking.

It must not become a hidden authentication system or a source of truth that overrides room context, presence, or safety policy.

---

## Why This Sub-Project Exists

Home Assistant today is strong at wake words, transcription, and intent routing.

It does not provide mature, mainstream, plug-and-play per-person speaker enrollment and matching as a first-class native feature.

Concierge needs a controlled voice identity layer to improve:

- greeting personalization
- responder election
- person-aware response style
- correction-driven learning

---

## Relationship To Person Identity

Voice recognition is one input to Identity Context.

It must be fused with:

- Home Assistant person entities
- presence and occupancy context
- room and interaction space context
- conversation ownership context
- profile preferences

Voice alone must never be treated as sufficient truth.

---

## Architectural Components

### Voice Enrollment

Enrollment is explicit and opt-in.

The system should capture a controlled set of samples for a household member.

Enrollment may begin from the people setup flow and continue later through a dedicated voice learning mode.

Enrollment outputs:

- voice profile
- enrollment confidence
- sample metadata
- consent state

Enrollment must be revocable.

---

### Speaker Embedding Matching

A speaker matching engine converts speech samples into embeddings and compares them to enrolled profiles.

Matching output should include:

- likely voice profile
- confidence
- top candidates
- attribution factors

Matching must remain explainable and bounded by policy.

---

### Voice Recognition Fusion

Speaker confidence must be fused with other identity signals.

Inputs may include:

- speaker embedding match
- BLE room proximity
- Aqara room presence
- active conversation owner
- room posture and activity

Fusion should produce one effective identity context.

---

### Learning Mode

Learning mode should guide a user through voice training.

It should support:

- enrollment consent
- sample capture
- retry prompts
- verification prompts
- deletion and reset paths

Learning mode must be understandable and reversible.

---

## Enrollment Lifecycle

1. person selects opt-in enrollment
2. Concierge explains purpose in plain language
3. speaker samples are captured
4. profile is created or updated
5. confidence is stored
6. corrections update the profile over time

---

## Runtime Rules

Voice recognition must:

- never block a deterministic action path only because voice confidence is low
- fall back to neutral interaction style when confidence is low
- preserve room-first resolution
- preserve multi-assistant arbitration rules
- never bypass safety confirmation policy

---

## Privacy And Trust Requirements

Requirements:

- explicit consent
- explicit delete path
- explicit disable path
- least-data retention
- explainable purpose
- bounded use inside Concierge only

Voice samples and voice profiles should remain inside the home network by default.

Raw audio handling must be documented and minimized.

---

## Success Criteria

- users can enroll voice identity intentionally
- Concierge can greet likely speakers by name when confident
- voice identity improves responder election and personalization
- learning remains reversible and explainable
- low-confidence behavior remains calm and neutral

---

## Final Principle

Voice recognition should make Concierge feel more personal and responsive without making it less predictable or less trustworthy.

See also: [identity-governance-reference.md](identity-governance-reference.md)
