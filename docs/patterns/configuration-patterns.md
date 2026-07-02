# Configuration Patterns

## Purpose

Configuration Patterns define how system configuration is managed, persisted, and exposed across Concierge.

They ensure a clear separation between:

- UI (user interaction)
- Store (source of truth)
- Runtime (execution)

These patterns prevent ambiguity, duplication, and inconsistent behavior.

---

## Core Principle

The UI is a projection of configuration.

The store is the source of truth.

Runtime executes based on the store.

---

## Configuration Layers

Configuration is divided into three layers:

1. Global Configuration (system-level)
2. Global Context Configuration (whole-home behavior)
3. Room Configuration (room-level behavior)

---

## Layer Responsibilities

### Global Configuration

Managed via:

- Home Assistant integration options (gear icon)

Defines:

- AI providers
- external connections
- system behavior rules

Rules:

- must not be modified through the main UI
- must not be used for interaction configuration

---

### Global Context Configuration

Managed via:

- Concierge UI (whole-home view)

Defines:

- weather
- news
- calendar
- email
- shopping list
- signal availability

Rules:

- must be user-visible
- must control availability, not data source logic

---

### Room Configuration

Managed via:

- room-specific UI

Defines:

- speakers
- execution preferences
- exposed entities
- enabled signals
- composite room participation

learned_values:

  lights:
    brightness:
  lamps:
    brightness:
  media:
    volume:
    last_media:
    last_genre
---
# LEARNED VALUE PATTERN

---

## Purpose

Defines how the system captures and reuses retained operational values over time.

Examples:

- learned lighting brightness
- learned media volume
- preferred speaker behavior
- room-scoped continue playing reference

These values are not user-authored configuration.

They represent stable, previously observed operating values that may be reused deterministically.

---

## Structure

learned_values:

  lights:
    brightness:

  media:
    volume:
    last_media:

  audio:
    speaker_profile:

---

## Rules

Learned values must:

- be captured during normal operation
- be stored in helper-backed state, dedicated retained-value storage, or runtime cache
- be reused by execution patterns (e.g. restore)

Learned values may be persisted, but only through controlled service or store paths.

Learned values must remain separate from user-authored configuration.

Learned values must not:

- be inferred without prior data
- introduce nondeterministic behavior

Runtime may read and apply learned values, but must not mutate configuration directly.

---
## UI → Store Pattern

### Rule

All user interaction must follow:

UI → Service Call → Validation → Store Write

---

### Requirements

- UI must never write directly to store
- all writes must go through services
- all changes must be validated before persistence

---

### Example

User selects preferred speaker:

1. UI triggers service call
2. service validates entity exists
3. store updates configuration
4. runtime reflects change

---

## Store → Runtime Pattern

### Rule

Runtime must only read from the store.

Runtime must not:

- modify configuration
- infer configuration
- create temporary overrides

---

### Example

When executing:

- runtime reads execution_preferences
- runtime executes directly
- no additional lookup or discovery

---

## UI Projection Pattern

### Rule

UI must reflect current store state.

UI must not:

- maintain independent state
- infer configuration outside store
- directly drive execution

---

### Behavior

UI displays:

- current configuration
- available options
- validation feedback

All actions must be routed through services.

---

## No Runtime Discovery Rule

Configuration exists to eliminate runtime discovery.

Runtime must not:

- scan entities dynamically per request
- infer relationships during execution
- build mappings on demand

All mappings must be:

- preconfigured
- stored
- reused

---

## Deterministic Configuration Rule

All configuration must be:

- explicit
- validated
- deterministic

The system must not:

- rely on naming conventions
- infer behavior from partial data
- guess configuration

---

## Execution Independence

Configuration defines execution targets.

Runtime executes them.

Example:

execution_preferences:
  shades:
    mode: scene
    target: scene.all_shades_closed

Runtime uses this directly.

UI does not trigger execution.

---

## Composite Configuration Pattern

Composite rooms must:

- be explicitly defined
- stored in configuration
- referenced during runtime resolution

Rules:

- must not be inferred dynamically
- must not alter underlying room model
- must validate all member rooms are on the same floor
- must reject cross-floor merged room definitions
- must persist merged room display name separately from member area ids
- must support composite membership edits (add/remove member rooms)
- must support composite rename without changing composite identity

Composite edit lifecycle rules:

- removing one member room must return that room to standalone room projection
- removing all member rooms must dismantle the composite and remove composite references
- composite snapshots must be recalculated after every membership change
- removed room devices must be excluded from composite device snapshots after update

UI projection requirements:

- merged composite replaces member room cards in main view projection
- composite projection must include member room name list for operator clarity

---

## Alias Integration Pattern

Voice phrases must use:

- entity names
- entity aliases (Home Assistant)

Configuration may:

- expose alias management
- write updates to Home Assistant

Configuration must not:

- create separate phrase systems
- override HA voice resolution

---

## External Source Configuration Pattern

External systems (M365, weather, news) must follow:

- connection setup → global configuration
- usage enablement → UI

Rules:

- authentication must remain in global config
- usage must be controlled in UI

---

## Validation Pattern

All configuration changes must:

- validate entity existence
- validate relationships (room, composite)
- validate execution targets

Invalid configuration must:

- be rejected
- provide clear feedback

---

## State Consistency Pattern

The system must maintain:

- a single source of truth (store)
- consistent projection in UI
- consistent behavior at runtime

Conflicts must not exist between:

- UI state
- store state
- runtime behavior

---

## Failure Handling

If configuration is missing:

- system must degrade gracefully
- runtime must skip unavailable features
- user must receive clear feedback

The system must not:

- fail execution
- attempt to infer missing configuration

---

## Performance Rules

Configuration must enable:

- direct execution
- minimal runtime processing
- precomputed mappings

The system must not:

- recompute configuration at runtime
- introduce latency through discovery

---

## Security Rules

Configuration must:

- protect sensitive data
- separate credentials from usage
- prevent exposure in UI

Sensitive data must only exist in:

- global configuration layer

---

## System Behavior Rules

The system must:

- enforce strict separation of UI and runtime
- rely on configuration for all decisions
- maintain deterministic operation

The system must not:

- allow UI to execute logic directly
- allow runtime to mutate configuration
- create hidden state

---

## Final Principle

Configuration defines what the system knows.

The UI exposes it.

Runtime executes it.

The system must never confuse these roles.
