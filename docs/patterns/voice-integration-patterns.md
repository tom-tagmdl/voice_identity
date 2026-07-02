# Voice Integration Patterns

## Purpose

Voice Integration Patterns define how Concierge integrates with Home Assistant's native voice system.

These patterns ensure that:

- Home Assistant remains the primary voice resolution system
- Entity names and aliases are the source of truth for phrases
- Concierge enhances orchestration without duplicating voice logic
- execution remains fast, deterministic, and predictable

---

## Core Principle

Home Assistant resolves what was said.

Concierge determines what to do with it when resolution is not direct.

---

## Alias-First Strategy

Voice interaction must follow an alias-first model.

Hierarchy:

1. Entity name
2. Entity aliases (Home Assistant)
3. Concierge orchestration (only if no direct match)

---

## Rules

The system must:

- use Home Assistant entity names and aliases as the primary phrase system
- rely on Assist (or voice integration) for natural language resolution
- prefer direct execution over orchestration

The system must not:

- create parallel phrase systems for entities
- override native resolution behavior
- duplicate alias handling logic

---

## Entity Voice Model

Each entity exposed to voice includes:

- name
- aliases
- exposure settings

Example:

entity: scene.close_afternoon_shades

name:
Close Afternoon Shades

aliases:
- afternoon shades
- block the sun
- close west shades

---

## Rules

- aliases must be defined and stored within Home Assistant
- Concierge must read, not duplicate, alias data
- alias changes must immediately influence behavior
- entity exposure must be respected

---

## Scene-Driven Voice Behavior

Scenes are the primary execution unit for voice interaction.

---

## Rules

- scenes must be directly invocable via name or alias
- scenes should define user-facing phrases
- scenes should represent complete, meaningful actions

Concierge must not:

- reinterpret scene intent
- modify scene behavior
- decompose scenes into individual actions

---

## Example

User:
Block the sun

Resolution:
alias → scene.close_afternoon_shades → scene.turn_on

---

## Phrase Resolution Flow

Voice processing must follow this deterministic flow:

1. Voice input received
2. Assist attempts entity/alias resolution

If match found:
  → concierge.execute_direct (direct execution)

If no match:
  → request passed to Concierge
  → Concierge resolves intent
  → execution occurs via execution patterns

---

## Resolution Outcomes

### Direct Resolution (Preferred)

Voice → Assist → entity/scene match → execution

- fastest path
- no Concierge overhead
- deterministic

---

### Concierge Resolution (Fallback)

Voice → no match → Concierge → execution mapping

Used for:

- multi-entity commands
- ambiguous phrasing
- contextual requests
- signal queries

---

## Concierge Fallback Behavior

Concierge handles:

- multi-entity commands
- grouped execution
- signal-based questions
- contextual interactions

Examples:

What should I do here  
Close everything  
Is the laundry done  

---

## Rules

- Concierge must only activate when entity resolution fails
- fallback must be deterministic
- fallback must not override valid entity matches
- fallback must use preconfigured execution targets

---

## Voice → Execution Bridge

Voice resolution must map directly to execution patterns.

Hierarchy:

1. Alias match → direct execution (scene/entity)
2. Execution preference → scene/group/entity
3. Concierge orchestration

---

## Rules

- execution must remain preconfigured
- no runtime decision of execution strategy
- must align with execution-patterns.md
- must maintain single-call execution where possible

---

## Multi-Assistant Responder Election

In homes with multiple voice assistants, more than one device may hear the same wake event.

Concierge must coordinate a single responder.

Rules:

- run a short responder election window
- select one primary responder using context signals
- suppress duplicate responses from non-primary responders
- preserve conversation ownership when a conversation is already active

Responder election inputs may include:

- interaction space confidence
- room proximity
- presence and likely speaker
- recent successful responder history
- posture constraints

---

## Speaker Attribution Pattern

Speaker attribution is optional but recommended for person-aware interaction quality.

Attribution output should include:

- person candidate
- confidence
- attribution factors

Rules:

- attribution must be treated as probabilistic context
- low-confidence attribution must fall back to neutral style
- attribution must not be used as authentication authority

---

## Person-Aware Style Pattern

When person context is available, Concierge may adapt response style.

Examples:

- direct and brief confirmations
- conversational and detailed summaries

Rules:

- style may change delivery, not action correctness
- style may not bypass safety confirmation requirements
- posture policy may override style to reduce disturbance

---

## Opt-In Learning Mode Pattern

Learning mode enables guided enrollment and adaptation.

Learning mode should support:

- explicit person consent
- optional voice training samples
- style preference setup
- correction capture for attribution and style tuning

Rules:

- enrollment must never be silent
- opt-out and profile deletion must be explicit
- adaptation must be reversible and explainable
- behavior shifts must be gradual, not abrupt

---

## Composite Room Interaction

When a command originates from a room:

- system resolves area_id
- checks for composite membership
- promotes to composite context when applicable

---

## Behavior

If direct entity match:
  → execute directly

If ambiguous:
  → Concierge resolves using room or composite context

Example:

User in kitchen:
Close the shades

Behavior:

- multiple entities available
- composite context applied
→ scene.all_shades_closed executed

---

## Scene vs Orchestration Decision

Decision hierarchy:

1. Direct entity or scene match → execute immediately
2. Alias match → execute immediately
3. No match → Concierge resolves using configuration

---

## Rules

- direct execution must always take precedence
- orchestration must not override explicit matches
- behavior must remain consistent across executions

---

## Alias Management

Aliases must be managed within Home Assistant.

Concierge may:

- display aliases in UI
- allow controlled alias editing
- write changes back to Home Assistant

Concierge must not:

- store independent phrase mappings
- create duplicate alias systems

---

## UI Integration

The Concierge UI must:

- display scenes and their aliases
- allow enabling or disabling exposure
- allow alias management within Home Assistant boundaries

Example:

Scene:
Close Afternoon Shades

Aliases:
- block the sun
- afternoon shades

Options:
- enable in this room
- include in composite behavior

---

## Performance Implications

Alias-first execution path:

Voice → Assist → Entity resolution → Service call

Results:

- minimal latency
- no additional processing
- direct execution

Concierge path:

Voice → no match → Concierge → execution

Used only when required.

---

## AI Usage Constraints

AI may assist with:

- disambiguation
- summarization
- contextual interpretation

AI must not:

- override alias resolution
- invent command mappings
- determine execution strategy
- execute actions

---

## Failure Handling

If voice input cannot be resolved:

- Concierge must respond clearly
- system must not guess intent

Example:

I am not sure what you want me to do.

---

## System Behavior Rules

The system must:

- prioritize native Home Assistant voice capabilities
- maintain deterministic execution
- preserve a single source of truth for phrases

The system must not:

- create competing voice systems
- introduce ambiguity between commands and scenes
- override user-defined aliases

---

## Relationship to Other Patterns

Voice Integration works with:

- execution-patterns.md (how actions run)
- configuration-patterns.md (how mappings are defined)
- runtime-architecture.md (execution flow)

---

## Final Principle

Entities define actions.

Aliases define how users speak.

Concierge ensures that when something cannot be resolved directly, it is resolved correctly—without replacing the underlying voice system.