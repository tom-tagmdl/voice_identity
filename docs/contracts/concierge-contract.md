# Concierge Contract

## Purpose

Concierge is the interaction and orchestration layer of the system.

It is responsible for how the home communicates, responds, and assists the user.

Concierge does not own data or logic. It coordinates capabilities exposed by other integrations.

---

## Core Responsibility

Concierge owns:

- User interaction (voice, UI prompts, questions)
- Orchestration across integrations
- Messaging and communication behavior
- Context awareness (room, user presence, mode)
- Person-aware interaction style application (when available)
- Decision about when and how to respond

Concierge does not own:

- Asset data
- Environment requirements
- Persistent state
- Evaluation logic

---

## System Role

Concierge acts as:

- The interface between the user and the system
- The orchestrator of integration capabilities
- The decision-maker for communication timing and modality

Concierge is not:

- A data store
- A decision engine for domain logic
- A system of record

---

## Data Boundaries

Concierge must never:

- Write directly to any system of record
- Store persistent asset or room data
- Perform evaluation of raw environment inputs

All data access must be:

- Read via exposed services or APIs
- Written via explicit service calls

---

## Service Interaction Rules

Concierge interacts with other integrations only through services.

Examples:

- Request asset data from Asset Intelligence
- Request environment recommendations
- Trigger updates via service calls

Concierge must:

- Never bypass service boundaries
- Never manipulate internal store structures
- Never assume data formats outside contract definitions

---

## Orchestration Model

Concierge is responsible for:

- Determining what capability is relevant
- Calling the appropriate service
- Combining results if needed
- Presenting the outcome to the user

Concierge must not:

- Reimplement logic already owned by another integration
- Duplicate evaluation rules
- Create conflicting interpretations of system state

---

## Communication Model

Concierge controls all communication using defined levels:

### Info
- Visual only
- No interruption

### Attention
- Visual plus optional voice
- Non-urgent

### Urgent
- Immediate voice
- Interruptive if required

### Night Mode
- Night behavior is determined by effective room posture
- In night posture, suppress all except urgent
- Global configuration may define the default night behavior, but rooms control the effective mode

### Quiet-Hours and Room Posture
- Quiet-hours is configured concierge-wide and defines the default suppression window
- Room posture remains room-wide and may increase suppression for that room at any time (for example: naps or early bedtime)
- Room posture overrides floor and concierge defaults for that room only
- Urgent delivery follows explicit global urgent bypass policy

---

## Scope Model

Concierge configuration is layered:

1. concierge-wide
2. floor-wide
3. room-wide

Effective resolution uses most-specific valid scope:

- room override
- else floor default
- else concierge default

This scope model must be used for communication behavior, execution target routing, and media/climate defaults.

Merged rooms (composites) are valid room-context targets and must route deterministically from any member area.

---

## Floor-Level Infrastructure Boundaries

Some capabilities are shared at floor scope and should not default to room scope.

Examples:

- thermostats and HVAC zone entities
- floor speaker groups
- floor media routing defaults

Room-level overrides remain allowed for explicit exceptions.

---

## Context Awareness

Concierge must be aware of:

- Room context (area)
- Available integrations and capabilities
- Active modes and posture (guest mode, room night posture, sleep posture, etc.)
- User intent (explicit or inferred)

Context must be:

- deterministic
- derived from system state
- not inferred unpredictably

---

## Person-Aware Interaction Boundaries

Concierge may apply person context to communication style.

Examples:

- concise responses for direct-style users
- richer detail for conversational-style users

Person-aware behavior must follow these rules:

- identity context may change delivery style
- identity context must not change foundational truth
- identity context must not bypass safety confirmation rules
- low-confidence identity must degrade to neutral style

Person-aware behavior must remain explainable and reversible.

Enrollment and consent rules are defined in person-identity-contract.md.

---

## Multi-Assistant Responder Responsibility

When multiple voice assistants hear the same request, Concierge must coordinate a single responder outcome.

Concierge must:

- evaluate room context and interaction space
- evaluate person-aware context when available
- elect one primary responder
- suppress duplicate responses
- preserve active conversation ownership where possible

This behavior must remain deterministic and explainable.

---

## AI Usage Rules

Concierge may use AI to assist with:

- natural language understanding
- summarization
- recommendation requests (delegated to integrations)

Concierge must not:

- allow AI to directly mutate system state
- make decisions that bypass contracts
- produce outputs that cannot be explained

All AI usage must:

- be bounded
- reference system data
- produce explainable results

---

## Capability Model

Concierge operates on capabilities exposed by integrations.

Examples:

- Asset Intelligence exposes asset and environment capabilities
- Future integrations may expose additional capabilities

Concierge must:

- discover available capabilities at startup or configuration time
- adapt behavior based on what is available
- avoid hard dependencies where possible

Discovery is allowed at startup or configuration time. Runtime must use precomputed results only.

---

## Global Context and Signal Integration

Concierge may orchestrate capabilities that represent whole-home context and household signals.

These include:

- Informational context (weather, time, news)
- Stateful signals (calendar, shopping list, appliance states, reminders)

These capabilities:

- Are owned and exposed by other integrations
- Must be accessed only via defined service interfaces
- Must not be stored or evaluated by Concierge

Concierge is responsible for:

- Determining when these signals are relevant to the user
- Routing requests to the appropriate integration
- Combining signal data into meaningful responses
- Delivering responses in a context-aware manner (room, time, mode)

Concierge must not:

- Directly interpret raw sensor or entity data
- Maintain independent copies of signal state
- Create conflicting representations of household state

---

## Failure Handling

Concierge must degrade gracefully when:

- required integrations are unavailable
- data is incomplete
- services fail

In these cases, Concierge should:

- provide a clear response
- avoid partial or misleading outputs
- never fabricate data

---

## System Behavior Rules

Concierge must:

- prioritize clarity over complexity
- prioritize usefulness over completeness
- only speak when necessary
- avoid repetition and noise

Concierge must never:

- overwhelm the user
- act without explanation
- assume data it does not have
- bypass validation in other integrations

---

## Final Principle

Concierge orchestrates understanding.

If a feature involves:

- communication
- interaction
- coordination across integrations

It belongs in Concierge.

If it involves:

- data ownership
- evaluation logic
- persistence

It does not belong in Concierge.