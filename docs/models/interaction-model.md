# Interaction Model

## Purpose

The Interaction Model defines how Concierge represents user-facing experiences at runtime.

Interactions are the mechanism through which the system presents:

- awareness (signals and context)
- actions (what can be done)
- workflows (guided steps)

Interactions are transient and must reflect only current, valid system state.

---

## Core Principle

Signals define what is true.

Context defines what is known.

Interactions define what is available to the user right now.

---

## Model Structure

An Interaction is represented as:

interaction:
  id:
  type:
  source:
  area_id:
  composite_id:
  summary:
  detail:
  actions:
  priority:
  state:
  created_at:
  updated_at:
  expires_at:

---

## Field Definitions

### id

A unique identifier for the interaction.

Rules:

- must be stable within its lifecycle
- must be unique per interaction instance

---

### type

Defines the category of interaction.

Valid types include:

- context_display
- signal_awareness
- actionable
- guided_workflow

---

### source

Defines the origin of the interaction.

Examples:

- signal.laundry
- context.weather
- context.news
- workflow.room_setup

Rules:

- must reference a valid system component
- must remain traceable

---

### area_id

The Home Assistant area associated with the interaction.

Rules:

- must match room context
- may be null if global

---

### composite_id

The composite room associated with the interaction (if applicable).

Rules:

- must be present when interaction is scoped to a composite
- must override area scope when set

---

### summary

A concise human-readable description.

Used for:

- UI display
- quick awareness
- compact views

Examples:

Laundry is complete  
You have 2 meetings today  
There are 5 items on your shopping list  

---

### detail

Optional expanded information.

Used for:

- detailed UI panels
- expanded context
- drill-down views

Examples:

Laundry finished 10 minutes ago  
Next meeting is at 2 PM with Project Team  

---

### actions

List of actions the user can take.

Structure:

actions:
  - id:
    label:
    service:
    confirmation_required:

Rules:

- actions must map to valid service calls
- must not contain business logic
- must be executable without interpretation

---

### priority

Defines ordering and urgency.

Values:

- urgent
- attention
- info

Rules:

- must be deterministic
- must influence ordering in UI
- must align with messaging model

---

### state

Defines lifecycle state of the interaction.

Values may include:

- active
- acknowledged
- completed
- expired

Rules:

- must be explicitly managed
- transitions must be deterministic

---

### created_at

Timestamp when interaction was created.

Must be:

- ISO 8601 UTC
- immutable

---

### updated_at

Timestamp of last update.

Must reflect:

- state change
- content update
- action execution

---

### expires_at

Defines when the interaction becomes invalid.

Rules:

- must be set when interaction is temporary
- must be respected by UI and runtime
- expired interactions must not be shown

---

## Interaction Types

---

### Context Display

Used for:

- weather
- news
- time

Characteristics:

- informational
- non-actionable (typically)
- user-requested or summary-driven

---

### Signal Awareness

Used for:

- laundry completion
- calendar updates
- reminders

Characteristics:

- state-driven
- may include simple actions
- may be passive or active

---

### Actionable

Used for:

- shopping list updates
- device control
- confirmations

Characteristics:

- action-first
- directly invokes services
- must confirm results

---

### Guided Workflow

Used for:

- room setup
- device configuration
- onboarding

Characteristics:

- multi-step
- stateful within session
- user-driven progression

---

## Interaction Lifecycle

---

### Creation

Interactions are created when:

- a signal changes
- a user makes a request
- a workflow is initiated

---

### Update

Interactions must update when:

- underlying signal changes
- action is executed
- additional detail is requested

---

### Expiration

Interactions must expire when:

- no longer relevant
- replaced by new interaction
- timeout reached

Rules:

- expiration must be deterministic
- stale interactions must not persist

---

### Removal

Interactions are removed when:

- dismissed by user
- expired
- source becomes invalid

---

## Relationship to Other Models

---

## Signals

Signals provide:

- state
- summary
- speakable output

Interactions expose this state to the user.

---

## Global Context

Context provides:

- informational data

Interactions present that data in user-facing form.

---

## Room Model

Room defines:

- where interaction is scoped
- which interactions are visible

---

## Execution Model

Actions within interactions:

- map directly to execution patterns
- must follow scene → group → entity hierarchy

---

## Voice Integration

Interactions must be accessible via:

- UI
- voice

Rules:

- voice must invoke same actions
- UI must reflect voice-triggered interactions

---

## Behavior Rules

Interactions must adapt presentation based on identity and content profile.

Content selection must:

- use integration-provided variants
- not alter underlying data
- remain deterministic

Interactions must:

- be derived from valid system state
- be deterministic
- be explainable

Interactions must not:

- store independent system state
- perform logic or evaluation
- exist without valid source data

---
## Conversation Context

---

### Purpose

Maintains short-lived interaction state to support follow-up requests.

---

### Structure

conversation_context:

  last_intent:
  last_entity:
  last_action:
  last_response:

---

### Rules

Conversation context must:

- be short-lived and session-based
- support clarification and follow-up

Conversation context must not:

- alter system state
- persist beyond interaction scope

---
Media interactions must:

- appear only when media is active
- reflect current context
- provide minimal, deterministic controls
- degrade gracefully when metadata is limited

---
## Failure Handling

If source data is unavailable:

- interaction must not be created
- or must degrade gracefully

If action fails:

- interaction must update with clear result

---

## Performance Rules

Interactions must:

- be generated without runtime discovery
- use precomputed runtime models
- be lightweight and ephemeral

---

## Final Principle

Interactions are the surface of the system.

They must always reflect:

- current truth
- available actions
- meaningful context

The system must never present an interaction that cannot be fulfilled.