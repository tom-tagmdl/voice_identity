# Room Model

## Purpose

The Room Model defines how physical spaces are represented and configured within the system.

A room is the central context that connects:

- environment sensing
- asset placement
- evaluation
- advisory
- interaction

---

## Core Principle

The room defines context.

Everything that happens in the system happens within a room.

---

## Room Identity

A room is defined by:

- area_id

Rules:

- area_id must match Home Assistant area
- area_id is the single source of truth for room identity
- no alternate identifiers may be used

---

## Room Layers

The room consists of three layers:

### 1. Configuration (stored)
### 2. Runtime Environment (derived)
### 3. Events and History

---

# 1. ROOM CONFIGURATION (STORED)

---

## Environment Configuration

Defines how the environment is constructed.

Fields include:

- sensor mappings by domain
- aggregation rules per signal

Example structure:

environment_config:
  climate:
    temperature:
      source_entities[]
      aggregation
    humidity:
      source_entities[]
      aggregation
    dew_point:
      source_entities[]
      aggregation

  light:
    lux:
      source_entities[]
      aggregation
    uv:
      source_entities[]
      aggregation

  air_quality:
    voc
    formaldehyde
    ozone
    no2

  particulates:
    pm25
    pm10

  biological:
    mold_index

  safety:
    leak

  structural:
    pressure
    vibration

  context:
    noise

  control_context:
    co2

---

## Configuration Schema Contract

Room configuration must use canonical structure and stable naming.

Required fields:

- area_id: string
- environment_config: object

Optional fields:

- windows: list
- room_alert_config: object

Rules:

- area_id must be non-empty and match Home Assistant area_id
- environment_config signal keys must use canonical names from environment model
- unknown signal keys must be rejected by validation
- configuration updates must follow service call -> validation -> store write

---

## Aggregation Rules

Each signal must define an aggregation method:

- mean
- min
- max

Rules:

- aggregation must be explicit
- no default implicit aggregation
- must be consistent across cycles

---

## Windows (Spatial Configuration)

Fields:

- windows[]

Each window may include:

- direction
- exposure_type

Rules:

- window direction must be explicitly defined
- no inferred spatial data
- windows influence exposure analysis

---

## Room Alert Configuration

Optional configuration for room-level behavior.

Fields may include:

- degraded monitoring thresholds
- alert suppression rules

Rules:

- must not override system-wide messaging patterns
- must remain bounded and explainable

---

# 2. RUNTIME ENVIRONMENT (DERIVED)

---
## Windows and Spatial Context

The room environment must include structured window data as part of the environment context.

Windows are not sensors, but they directly influence environmental interpretation and exposure.

---

### Windows Structure

The environment snapshot must include:

windows:
  entries:
    - window_id
      direction
      exposure_type (optional)

---

### Window Direction

Window direction defines orientation relative to the compass:

- north
- northeast
- east
- southeast
- south
- southwest
- west
- northwest

Rules:

- direction must be explicitly configured
- direction must not be inferred automatically
- direction must be used in exposure calculations

---

### Multiple Windows

Rooms may contain multiple windows.

Rules:

- all windows must be listed
- order does not imply importance
- exposure logic may evaluate each window independently

---

### Relationship to Environment

Windows must appear alongside environment data in the same snapshot.

Windows are part of:

- spatial context
- exposure modeling
- advisory generation

---

### Relationship to Exposure Analysis

Window data may be combined with:

- sun position (azimuth and elevation)
- asset placement
- room orientation

To derive:

- directional exposure
- light amplification
- exposure risk

Derived values are runtime only and must not be persisted.

---

### Relationship to Asset Placement

Exposure depends on both:

- room window orientation
- asset placement within the room

Example:

- asset near southwest window
- sun azimuth matches window direction

This may increase light exposure risk.

---

### Rules

Windows must:

- be explicitly configured
- be included in environment snapshot
- be used in spatial and exposure modeling

Windows must not:

- be inferred without configuration
- be treated as sensor data
- directly generate risk without evaluation logic

---

### Final Principle

Windows define exposure potential.

They do not represent conditions.

They must always be combined with environment data and asset placement to derive meaning.

## Environment Snapshot

The room produces a single environment snapshot per evaluation cycle.

This snapshot includes:

- all environment domains
- confidence level
- source status
- last updated time

Rules:

- exactly one snapshot per room per cycle
- shared across all assets in the room
- must be deterministic

Snapshot contract:

- snapshot must include all required environment domains
- confidence must use enum: GOOD | PARTIAL | DEGRADED | STALE
- last_updated must be ISO 8601 UTC timestamp (ending with Z)
- source_status must be present with stable schema

---

## Confidence

Confidence reflects:

- data completeness
- sensor availability
- data freshness

Values:

- GOOD
- PARTIAL
- DEGRADED
- STALE

Rules:

- must be included in every snapshot
- must influence evaluation and advisory behavior
- must follow precedence: STALE > DEGRADED > PARTIAL > GOOD
- identical inputs must produce identical confidence results

---

## Source Status

Tracks:

- available sensors
- unavailable sensors
- stale sensors
- aggregation applied

Rules:

- used for explainability
- must not drive decision logic directly

Minimum schema:

source_status:
  configured_sources: number
  unavailable_sources: number
  stale_sources: number
  missing_configuration: string[]
  aggregation:
    <domain>.<signal>: mean | min | max | none

Rules:

- source_status must be present for every room snapshot
- counts must be non-negative integers
- aggregation keys must use canonical signal naming

---

# 3. ASSET RELATIONSHIP

---

## Room to Asset Mapping

Each asset must:

- reference area_id
- inherit room environment context

Rules:

- assets do not define environment
- assets do not override room context
- assets are evaluated using room snapshot

---

## Shared Evaluation Context

For each evaluation cycle:

- one room snapshot is created
- all assets in the room use that snapshot

This ensures:

- consistency
- determinism
- no drift between assets

Deterministic evaluation order:

- assets in a room must be evaluated in lexical order by asset_id
- event generation must follow evaluation order for equal-priority outputs

---

# 4. SPATIAL CONTEXT

---

## Derived Spatial Data

The system may derive spatial context using:

- window direction
- sun position
- asset placement

Derived outputs may include:

- directional light exposure
- azimuth alignment
- elevation impact

Rules:

- derived values must not be persisted
- derived values must be explainable
- derived values must not alter configuration

---

# 5. EVENT MODEL

---

## Room-Level Events

Room events may include:

- environment updates
- confidence changes
- configuration changes
- spatial updates

Required event linkage:

- cycle_id
- sequence_in_cycle
- correlation_id (when generated from service flow)

---

## Event Rules

Events must be:

- timestamped
- immutable
- structured

Events must not:

- be modified once written
- be duplicated

Ordering rules:

- primary: timestamp ascending
- tie-break: cycle_id, then sequence_in_cycle, then event_id lexical

---

# 6. RELATIONSHIP TO OTHER MODELS

---

## Room and Environment Model

The room produces the environment model.

The environment model must:

- reflect configured sensors
- be computed per room
- remain independent of evaluation

---

## Room and Asset Model

The room provides context for assets.

Assets depend on:

- room environment
- room configuration
- spatial context

---

## Room and Advisory

The room may generate advisory at the room level.

Examples:

- unsuitable room conditions for asset types
- missing sensors
- environmental instability

Rules:

- advisory must not mutate room configuration
- advisory must remain optional
- room-level advisory must be produced by advisory/evaluation outputs, not by UI logic

---

## Room and AI

AI may:

- suggest sensor additions
- recommend configuration improvements
- propose spatial adjustments

AI must not:

- modify room configuration directly
- bypass validation
- invent spatial data

---

# 7. FAILURE HANDLING

If room configuration is incomplete:

- environment must still be generated
- confidence must be reduced
- evaluation must continue

The system must never:

- fail due to missing sensors
- assume values not provided
- produce undefined output

---

# 8. CONCIERGE PROJECTION

---

## Purpose

The Concierge Projection defines how a room is exposed to the Concierge interaction layer.

This layer does not influence environment modeling, asset evaluation, or system state.

It defines how the room is experienced by the user through voice and UI.

---

## Core Principle

The room defines context.

Concierge defines how that context is revealed.

---

## Projection Model

The Concierge Projection includes:

- available devices and entities
- preferred communication outputs (speakers)
- exposed sensors and capabilities
- global context overlays
- signal availability within the room

This projection is derived and must not alter room configuration.

---

## Projection Structure

The room may expose a Concierge Projection structure:

concierge_projection:
  available: boolean
  preferred_speaker:
  speaker_candidates[]:
  voice_devices[]:
  exposed_entities[]:
  exposed_sensors:
  enabled_signals:
  global_overlays:

---

## Field Definitions

### available

Indicates whether Concierge interaction is enabled for the room.

---

### preferred_speaker

The primary audio output device for Concierge in this room.

Rules:

- must reference a valid media player entity when available
- must not be inferred without confirmation
- may be selected via UI or voice workflow

Fallback behavior:

- if no preferred speaker is defined
- and no speaker_candidates are available

Concierge must fall back to:

- the speaker associated with the invoking voice device

This ensures:

- deterministic response behavior
- no loss of voice interaction capability
- consistent user experience across all rooms

Concierge must always prefer:

1. explicitly configured preferred_speaker
2. discovered speaker_candidates
3. voice device speaker (fallback)

This ordering must be strictly enforced and must not vary across executions.

---

### speaker_candidates

List of eligible speaker entities within the room.

Derived from:

- media_player domain
- room association via area_id
- label-based filtering (optional)

If speaker_candidates is empty:

- the room is considered to have no dedicated audio output
- fallback behavior must be used via the invoking voice device
---

### voice_devices

Voice assistant devices associated with the room.

Used to:

- resolve room context from user interaction
- enable voice-driven configuration

---

### exposed_entities

Entities that Concierge may reference for interaction.

Examples:

- lights
- covers
- switches
- media devices

Rules:

- derived from room inventory
- filtered by domain or label
- must not include unsupported or unavailable entities

---

### exposed_sensors

Defines which environmental or system sensors are available to Concierge.

Structure:

exposed_sensors:
  temperature: boolean
  humidity: boolean
  noise: boolean
  light: boolean
  air_quality: boolean

Rules:

- sensors must exist in environment configuration
- exposure must be explicitly enabled
- missing sensors must result in graceful absence

---

### enabled_signals

Defines which Signals are available in this room.

Examples:

- calendar
- shopping_list
- laundry
- dishwasher

Rules:

- signals are global but may be enabled or disabled per room
- signals must be accessed via the Signal Contract
- Concierge must respect room-level enablement

---

### global_overlays

Defines which Global Context sources are available in the room.

Examples:

- weather
- news
- time

Rules:

- context is global and must not be duplicated
- overlay only controls visibility and usage within the room

---

## Derivation Rules

The Concierge Projection must be derived from:

- Home Assistant area and entity model
- integration-provided data
- room configuration
- Concierge-specific configuration (stored externally)

The Room Model must not persist Concierge configuration directly.

---

## Interaction Responsibilities

Concierge uses the room projection to:

- determine what can be controlled
- determine what can be asked
- select appropriate output devices
- route requests to the correct services

---

## Separation of Concerns

The Room Model must not:

- store speaker selections
- store signal state
- store global context
- perform interaction logic

The Concierge Projection must not:

- modify environment configuration
- influence evaluation or advisory
- alter asset relationships

---

## Relationship to Other Models

### Room Model

Provides:

- physical context
- environment configuration
- spatial structure

### Signal Model

Provides:

- household state

### Global Context

Provides:

- ambient information

### Concierge

Combines all of the above into interaction behavior.

---

## Failure Handling

If projection data is incomplete:

- room remains valid
- Concierge capabilities are reduced
- interaction must degrade gracefully

Examples:

- no speaker → no voice output
- no sensors → no environment questions
- no signals → no household state queries

---
### audio_overrides

Defines room-specific audio behavior during Concierge interactions.

Structure:

audio_overrides:
  tts_volume:
  duck_level:
  restore_after:

---

#### tts_volume

Overrides the global TTS volume for this room.

---

#### duck_level

Overrides the global ducking level when media is active.

---

#### restore_after

Controls whether media returns to its previous state after TTS.

---

## Rules

Room audio behavior must:

- override global configuration when defined
- remain deterministic
- be applied consistently

The system must apply audio configuration in this order:

1. room override
2. global audio configuration

---

## Runtime Behavior

During voice interaction:

1. determine speaker (existing logic)
2. resolve audio behavior (room → global)
3. capture current media state
4. apply ducking (if enabled)
5. set TTS volume
6. deliver speech
7. restore prior state (if configured)

---

## Constraints

Audio handling must:

- not delay execution
- not require runtime discovery
- use precomputed configuration

---
### retained_operational_values

Defines room-scoped values captured from prior stable behavior for later deterministic reuse.

Structure:

retained_operational_values:
  lights:
    brightness:
  lamps:
    brightness:
  media:
    volume:
    last_media:
    last_genre:

---

Examples:

- last stable lamp brightness in this room
- last stable light brightness in this room
- last played media reference for continue playing

---

## Rules

Retained operational values must:

- be room-scoped when the originating behavior is room-scoped
- be captured deterministically from prior valid behavior
- be reusable without runtime inference

Retained operational values must not:

- be treated as user-authored configuration
- alter execution rules
- become a second source of truth for media or device state
---
### identity_overrides

Defines room-specific overrides for interaction behavior.

Structure:

identity_overrides:
  persona:
  tts_voice:
  verbosity:

---

## Rules

Room identity overrides:

- take precedence over global identity configuration
- must be optional
- must not override execution behavior

---

## Resolution Order

Interaction identity must be resolved as:

1. room override
2. user profile
3. global default

---
### room_posture

Defines the behavioral mode of the room.

---

Structure:

room_posture:
  mode:

---

Examples:

- day
- night
- sleep
- away

---

Rules:

- posture influences interaction behavior
- posture must not alter execution determinism

---
## Final Principle

The room defines what exists.

The Concierge Projection defines what is accessible.

Concierge ensures the user only experiences what is valid, available, and meaningful.

---
---

# 9. COMPOSITE ROOM CONTEXT

---

## Purpose

Composite Room Context defines how multiple rooms (areas) may be combined into a single logical interaction space.

This allows Concierge to:

- treat multiple areas as one experience
- unify device control across rooms
- provide consistent audio and interaction behavior

---

## Core Principle

A composite room is a virtual construct.

It does not replace physical rooms.

It overlays them for interaction purposes.

---

## Composite Structure

A composite room is defined as:

composite_room:
  id:
  areas[]:
  name:
  primary_area:
  shared_audio:
  shared_controls:

---

## Field Definitions

### id

Unique identifier for the composite room.

Must be stable and user-defined.

---

### areas

List of Home Assistant area_ids included in the composite.

Rules:

- all entries must map to valid areas
- order does not imply priority
- duplication is not allowed

---

### name

Human-readable name.

Example:

Great Room

---

### primary_area

The default area used for:

- context resolution
- fallback decisions

Rules:

- must exist within areas[]
- must be explicitly defined

---

### shared_audio

Defines how speakers behave across the composite.

Options may include:

- grouped playback (e.g., Sonos group)
- preferred speaker set across areas

Rules:

- must follow audio routing hierarchy
- must support fallback behavior

---

### shared_controls

Defines whether actions apply across all areas.

Examples:

- shades
- lights
- media

Rules:

- must be explicit
- must not assume all entities apply universally
- must respect entity availability per area

---

## Behavior Rules

When a composite room is active:

- all included areas are considered in scope
- inventory must include entities from all areas
- actions must apply across all applicable entities

Example:

Command:
Close the shades

Behavior:
Applies to all shade entities across kitchen, living room, and dining room

---

## Inventory Aggregation

Composite room inventory is derived as:

- union of entities from all areas
- filtered for availability
- categorized using labels and domains

Rules:

- no duplication of entities
- must maintain deterministic ordering
- must reflect real-time state

---

## Audio Behavior

Audio routing must follow:

1. composite preferred speaker/group
2. area-level speaker candidates
3. voice device fallback

Rules:

- must remain deterministic
- must preserve existing audio hierarchy
- must support grouped playback where available

---

## Context Resolution

When resolving room context:

- system must detect if the area belongs to a composite
- if so, promote context to the composite level

Example:

User speaks in kitchen

System resolves:

Kitchen → part of Great Room → use composite context

---

## Interaction Behavior

Composite rooms must:

- expose a single interaction surface
- aggregate signals and context
- provide unified UI view

Rules:

- interactions must not duplicate across areas
- signals remain global and unaffected
- context remains global and unaffected

---

## Configuration Rules

Composite rooms must be:

- explicitly configured by the user
- stored outside of the Room Model (Concierge-controlled)

Room Model must not persist composite definitions.

---

## Separation of Concerns

Composite rooms:

- belong to Concierge interaction layer
- do not modify environment modeling
- do not alter asset relationships

---

## Failure Handling

If one area is unavailable:

- composite room remains functional
- available areas must still respond

If all areas are unavailable:

- composite must degrade gracefully

---

## Final Principle

Physical rooms define structure.

Composite rooms define experience.

The system must support both without conflict.

---

# FINAL PRINCIPLE

The room defines context.

The environment describes conditions.

Assets define requirements.

Evaluation determines risk.

All system behavior must flow through the room.