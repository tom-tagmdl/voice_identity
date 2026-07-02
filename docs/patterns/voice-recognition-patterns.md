# Voice Recognition Patterns

## Purpose

Voice Recognition Patterns define how Concierge enrolls, attributes, and adapts to speaker identity.

These patterns ensure that voice recognition is:

- opt-in
- confidence-based
- explainable
- reversible
- aligned with room context and presence

---

## Core Principle

Voice recognition improves interaction quality.

It must not become hidden surveillance or a replacement for room and presence context.

---

## Pattern 1: Opt-In Enrollment

Enrollment must be explicitly initiated by the person.

Rules:

- explain the purpose in plain language
- require consent before sample capture
- provide clear disable and delete actions
- allow re-enrollment after reset

---

## Pattern 2: Guided Voice Training

Learning mode should guide the person through sample capture.

Rules:

- capture multiple samples
- allow retries
- verify the enrolled identity
- keep the flow short and understandable

---

## Pattern 3: Speaker Attribution With Confidence

Speaker attribution must emit confidence and candidates.

Rules:

- high confidence may personalize the greeting
- medium confidence should be cautious
- low confidence must fall back to neutral style

---

## Pattern 4: Fusion With Presence And Room Context

Voice matching should never stand alone.

It should be fused with:

- room presence
- BLE proximity
- active conversation ownership
- room posture

---

## Pattern 5: Household Learning Loop

The system may learn from corrections and successful matches.

Examples:

- "that was me"
- "that was David"
- "you got the wrong person"

Rules:

- learning must be reversible
- learning must be gradual
- learning must be explainable

---

## Pattern 6: Greeting Behavior

When confidence is sufficient, Concierge may greet the person by name.

Example:

"Hello Tom, I’m listening."

Rules:

- only one responder may greet
- night posture may suppress speech
- low confidence uses a neutral greeting

---

## Pattern 7: Profile Updates From Conversation

Concierge may offer to save style or identity updates after a conversation.

Examples:

- "Do you want me to keep responding this way?"
- "Should I remember that you prefer brief responses?"

Rules:

- updates must be explicit
- updates must be reversible
- updates must remain human understandable

---

## Pattern 8: Respectful Fallback

If the system is unsure who is speaking:

- address the user neutrally
- continue deterministically
- avoid false certainty

---

## Final Principle

Voice recognition should make Concierge feel attentive and personal while preserving calm, predictability, and trust.
