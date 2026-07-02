# Composite Room Contract

## Purpose

The Composite Room Contract defines how multiple physical rooms (Home Assistant areas) are combined into a single logical interaction space.

Composite rooms enable Concierge to:

- treat multiple areas as one context
- unify control across rooms
- provide consistent interaction and execution behavior
- optimize performance through shared execution strategies

Composite rooms do not replace physical rooms. They extend them.

---

## Core Principle

Physical rooms define structure.

Composite rooms define experience.

---

## Definition

A Composite Room is a virtual construct that groups multiple Home Assistant areas into a single interaction context.

It is used exclusively by Concierge and must not modify underlying Home Assistant area definitions.

Merged room is an allowed user-facing term for a Composite Room.

Example:

- Upstairs Public Space = Kitchen + Dining Room + Living Room

---

## Composite Structure

A Composite Room is defined as:

composite_room:
  id:
  name:
  areas:
  primary_area:
  execution_preferences:
  audio_configuration:
  enabled:
  created_at:
  updated_at:

---

## Field Definitions

### id

Unique identifier for the composite room.

Rules:

- must be stable
- must not conflict with area_id values

---

### name

Human-readable name for the composite.

Examples:

- Great Room
- Downstairs
- Main Living Area

---

### areas

List of Home Assistant area_ids included in the composite.

Rules:

- all values must map to valid areas
- duplication is not allowed
- order must not imply priority
- all member areas must belong to the same floor
- cross-floor composite membership is not allowed

---

### primary_area

Defines the default reference area.

Used for:

- fallback logic
- context anchoring
- default entity resolution

Rules:

- must exist within areas
- must be explicitly defined

---

### execution_preferences

Defines how actions are executed across the composite.

Structure:

execution_preferences:
  <capability>:
    mode:
    target:

Modes:

- scene
- group
- entity

Rules:

- must follow execution hierarchy
- must be explicitly configured
- must not be inferred at runtime

---

### audio_configuration

Defines how audio is handled.

Structure:

audio_configuration:
  preferred_speaker:
  speaker_group:
  fallback_enabled:

Rules:

- must follow global audio routing rules
- must support speaker grouping when available
- must support fallback to voice device

---

### enabled

Boolean indicating whether composite is active.

Rules:

- disabled composites must be ignored by runtime
- must not affect physical rooms

---

### created_at / updated_at

Timestamps for lifecycle tracking.

Rules:

- must be ISO 8601 UTC
- must reflect creation and modification

---

## Context Resolution

When resolving a room:

1. Identify area_id from invoking device
2. Check if area belongs to a composite
3. If yes:
   → promote to composite context
4. If no:
   → use area context

Rules:

- composite context must override area context
- resolution must be deterministic

### Voice Invocation Rule

If any voice assistant device in any member area is invoked, context must resolve to the composite when that area belongs to an enabled composite.

This means a request from Kitchen, Dining Room, or Living Room voice endpoints resolves to the same merged room context when those areas are part of the same composite.

Resolution must not depend on which member room started the request.

---

## Inventory Aggregation

Composite room inventory must be derived as:

- union of all entities across areas
- filtered for availability
- categorized by domain and labels

Rules:

- entities must not be duplicated
- ordering must be deterministic
- state must reflect real-time values

All controllable entities in member areas are considered part of the merged room execution inventory unless explicitly excluded by configuration.

---

## Execution Behavior

Composite rooms must use aggregated execution.

Rules:

- prefer composite-level scenes
- fallback to group-based execution
- fallback to entity-level execution

Execution must:

- be performed with a single service call when possible
- avoid per-room iteration

For merged room execution, actions must target the aggregated entity set for all member areas.

The system must not require room-by-room manual invocation once a merged room is resolved.

---

## Example

Command:
Close the shades

Composite:
Kitchen + Living Room + Dining Room

Execution:

- scene available → scene.turn_on
- else group → cover control
- else entity → batched call

---

## Audio Behavior

Audio must follow hierarchy:

1. composite preferred speaker or group
2. area-level speaker candidates
3. voice device speaker fallback

Rules:

- must be deterministic
- must not delay execution

---

## Interaction Behavior

Composite rooms must:

- expose a single interaction surface
- aggregate signals and context
- avoid duplicate interactions

Rules:

- signals remain global
- context remains global
- interactions must be unified

---

## Relationship to Other Models

---

### Room Model

Defines:

- physical structure
- environment configuration

Composite does not modify this.

---

### Signal Model

Signals remain global and unaffected by composites.

Composite affects only visibility and interaction.

---

### Interaction Model

Interactions generated for a composite:

- must appear as one set
- must not duplicate across areas

---

### Execution Patterns

Execution must follow:

- scene → group → entity hierarchy
- preconfigured execution strategy

---

## Configuration Rules

Composite rooms must be:

- explicitly created by the user
- stored in Concierge configuration
- independent of Home Assistant area model

Main Concierge UI may expose merged room creation from room cards.

When merged room projection is active in main view:

- one composite tile replaces member room tiles
- composite tile includes member room names for quick reference

Composite edit operations must support:

- renaming the composite
- removing one or more member rooms
- full composite dismantle when no member rooms remain

When member rooms are removed:

- removed rooms return to standalone room projection
- composite inventory must be recalculated using remaining member areas only
- removed room devices must not remain in composite inventory or selectors

Composite definitions must not be:

- inferred automatically
- derived from naming conventions

---

## Failure Handling

If one area is unavailable:

- remaining areas must continue to function

If all areas are unavailable:

- composite must degrade gracefully

If execution fails:

- fallback strategy must be used

---

## System Behavior Rules

Composite rooms must:

- remain deterministic
- improve performance through aggregation
- maintain consistent user experience

Composite rooms must not:

- alter underlying entity behavior
- introduce execution ambiguity
- duplicate logic across areas
- retain stale room device references after membership changes

---

## Final Principle

Composite rooms unify interaction without changing structure.

They provide a higher-level experience that reflects how users think about their home, not how the system is physically defined.
