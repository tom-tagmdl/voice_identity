# Person Identity Patterns

## Purpose

Person Identity Patterns define how Concierge applies person-aware behavior in runtime interaction.

These patterns ensure:

- personalization improves interaction quality
- deterministic execution remains intact
- style adaptation remains transparent and bounded

---

## Core Principle

Personalize delivery, not truth.

Concierge may adapt tone, detail, and follow-up behavior by person.

Concierge must not adapt foundational truth or safety rules by person.

---

## Pattern 1: People Tiles In Setup

The setup experience should support two setup tracks:

- rooms and areas
- people

People should be represented with people tiles, similar to room tiles.

People tile goals:

- make person preference setup explicit
- keep setup understandable and approachable
- avoid hiding personalization in advanced screens

People tiles should also surface linked identity and presence devices.

---

## Pattern 2: Guided Person Preference And Device Setup

Each people tile should allow:

- style selection
- channel preference selection
- follow-up preference selection
- override and reset controls
- BLE proximity device linking
- Aqara room presence device linking

Setup should include plain-language examples for each style choice.

Device choices should be split into:

- identity devices: iPhone, watch, and other BLE sources tied to the person
- supporting presence devices: room presence sensors that help reinforce location confidence

---

## Pattern 3: Optional Learning Mode

Learning mode must be optional and consent-based.

Learning mode should support:

- person identification confirmation prompts
- style preference confirmation prompts
- optional voice sample enrollment
- correction capture from real interactions
- device linking during enrollment

Learning mode must provide clear disable and delete paths.

---

## Pattern 4: Multi-Assistant Responder Election

When multiple assistants hear the same wake event:

- run responder election
- select one primary responder
- suppress duplicate responses

Election inputs should include:

- interaction space confidence
- person proximity and presence
- active conversation owner
- room posture
- recent successful ownership

---

## Pattern 5: Relaxed Command Handling

Relaxed commands should work when room context is strong.

Example:

"open the shade"

Resolution should:

- use active room and merged space scope first
- resolve local controllable entities first
- execute immediately when unambiguous

If ambiguous, use concise clarification or respectful redirect.

---

## Pattern 6: Respectful Redirect

When target is outside local scope:

- explain context in plain language
- ask one confirmation question
- execute cross-room only if confirmed

Example:

"I think the shade you mean is in another room. Do you want me to open it there?"

---

## Pattern 7: Mid-Conversation Style Adjustment

Concierge should support in-session style adjustment.

Examples:

- "be brief"
- "tell me more"
- "skip follow-up questions"

Rules:

- apply session override immediately
- preserve action determinism
- offer to save adjustment as a profile preference

---

## Pattern 8: Posture-Aware Personalization

Room posture may override person style where needed.

Examples:

- nighttime posture suppresses non-urgent TTS
- quiet posture routes to dashboard even for conversational users

Rules:

- posture and safety have higher priority than style verbosity
- user experience should remain calm and low-noise

---

## Pattern 9: Explainability Rendering

Machine explainability must be available for diagnostics.

User-facing explainability must be plain language.

Examples:

- machine: reason code and confidence fields
- user: "I responded here because this room is active and you were detected nearby."

---

## Pattern 10: Correction-Driven Adaptation

Use explicit and implicit corrections to improve behavior.

Correction examples:

- "wrong room"
- "wrong person"
- "be less chatty"

Rules:

- adapt gradually
- adapt reversibly
- log adaptation rationale
- avoid sudden behavior shifts

---

## Final Principle

Person-aware behavior should reduce friction and increase comfort while keeping Concierge deterministic, transparent, and trustworthy.
