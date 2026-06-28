# Asset Model

## Purpose

The Asset Model defines the complete representation of an asset in the system.

An asset represents any physical object whose condition, location, and environment matter.

This model defines:

- what is stored
- what is derived
- what is evaluated
- what is historical

---

## Core Principle

An asset defines requirements.

The system determines state.

---

## Model Layers

The asset model consists of three layers:

### 1. Persistent Model (stored)

Data saved in the system of record.

### 2. Runtime Projection (derived, not stored)

Current calculated state.

### 3. Historical Events

Immutable record of changes and observations.

---

# 1. PERSISTENT MODEL

This is the stored asset record.

---

## Identity

Fields:

- asset_id
- name
- asset_type

Rules:

- asset_id must be unique and stable
- asset_type should support classification and policy

---

## Metadata

Fields:

- labels
- description:

  general:
    summary:
    detail:

  technical:
    summary:
    detail:

  advisory:
    summary:
    detail:
- manufacturer
- warranty

## Description Variants

Assets may expose multiple description variants based on audience.

---

## Types

### general

Human-friendly, easy to understand.

Example:
"The air is a bit too humid for this item."

---

### technical

Precise, data-driven explanation.

Example:
"Humidity exceeds recommended preservation threshold."

---

### advisory

Guidance-oriented explanation.

Example:
"Consider lowering humidity to prevent long-term damage."

---

## Rules

Descriptions must:

- be provided by the integration (not generated at runtime)
- represent the same underlying condition
- differ only in presentation and framing

Descriptions must not:

- conflict with each other
- represent different system states
- introduce new or inferred data

Rules:

- metadata is descriptive only
- no logic may exist here

---

## Placement

Fields:

- area_id
- near_window
- facing_direction
- exposure_zone
- placement_description
- location_detail

Rules:

- every asset must belong to a room
- placement must be explicitly defined
- no inferred placement

---

## Enclosure

Fields:

- enclosure_type
- enclosure_sealed

Rules:

- enclosure influences environmental exposure
- enclosure must not be inferred automatically

---

## Environment Requirements

Fields (by domain):

- climate:
  - temperature_min
  - temperature_max
  - humidity_min
  - humidity_max
  - dew_point_min
  - dew_point_max

- light:
  - lux_min
  - lux_max
  - uv_min
  - uv_max

- air_quality:
  - voc_max
  - formaldehyde_max
  - ozone_max
  - no2_max

- particulates:
  - pm25_max
  - pm10_max

- biological:
  - mold_index_max

Rules:

- all values must be bounded
- all values must be validated before storage
- requirements represent desired conditions, not current ones

---

## Debounce Policy

Fields:

- red_transition_seconds
- recovery_seconds

Rules:

- debounce controls stability of risk transitions
- must be persisted as part of asset policy
- must not be embedded in evaluation logic

---

## Custody

Fields:

- status
- holder
- location_detail
- effective_at
- loans

Rules:

- custody tracks lifecycle and ownership
- must be historically auditable

---

## Financial

Fields:

purchase:
- purchase_date
- purchase_price
- source
- notes

valuation:
- estimated_value
- valuation_date
- method
- notes

Rules:

- financial data is optional but structured
- must not influence evaluation directly unless explicitly modeled

---

## Documents

Fields:

- digital_documents
- physical_documents

Rules:

- only metadata stored in asset
- actual file handling externalized
- must support multiple providers over time

---

## Links

Fields:

- device_id
- tracker_entity_id

Rules:

- links connect assets to HA ecosystem
- must not create runtime coupling

---

# 2. RUNTIME PROJECTION (NOT STORED)

This data is derived by the coordinator.

---

## Environment Context

Fields:

- room_environment_snapshot
- confidence

---

## Risk State

Fields:

- current_state (GREEN, AMBER, RED, UNCONFIGURED)
- candidate_state (GREEN, AMBER, RED, UNCONFIGURED, null)
- evaluated_at
- state_since

Rules:

- evaluated_at must be ISO 8601 UTC timestamp (ending with Z)
- state_since must be ISO 8601 UTC timestamp (ending with Z) or null
- current_state must always be present
- candidate_state may be null when no transition is pending
- UNCONFIGURED is allowed only when required limits are not defined

---

## Risk Explanation

Fields:

- reasons[]
- contributing_signals

Rules:

- must be explainable
- must match evaluation inputs

---

## Exposure Analysis

Fields:

- exposure_risk_level
- azimuth
- elevation
- directional_match
- current_lux
- current_uv

Rules:

- derived from spatial + environment model
- must not be stored

---

## Advisory Output

Fields:

- primary_message
- recommendations[]
- advisory_type

Rules:

- advisory must not mutate asset
- advisory must be explainable

---

# 3. HISTORICAL EVENTS

Stored separately from asset record.

---

## Event Types

- environment_event
- risk_state_changed
- advisory_event
- custody_event
- document_event
- configuration_event

---

## Event Rules

Events must be:

- immutable
- timestamped
- versioned
- traceable to source

Events must never:

- be modified after creation
- be duplicated

---

# RELATIONSHIP MODEL

---

## Asset and Environment

- assets do not generate environment
- assets consume environment

All assets in the same room must use:

- a single environment snapshot per cycle

---

## Asset and Evaluation

Evaluation compares:

- environment snapshot
- asset requirements

Assets do not evaluate themselves.

---

## Asset and Advisory

Advisory suggests improvements.

Advisory must not:

- modify asset state directly
- bypass validation

---

## Asset and AI

AI may assist with:

- requirement suggestions
- explanation generation

AI must not:

- write to asset directly
- bypass validation services

All AI output must be validated before application.

---

# SERVICE MODEL

All updates must follow:

Service call -> Validation -> Store write -> Coordinator refresh

No direct mutation allowed.

---

# VALIDATION RULES

All asset writes must:

- validate schema
- validate ranges
- enforce required fields

Failures must:

- reject entire operation
- not partially apply changes
- return clear errors

---

# FAILURE HANDLING

If asset data is incomplete:

- asset remains valid
- evaluation degrades gracefully
- advisory may recommend completion

System must never:

- corrupt asset state
- lose history
- produce undefined behavior

---
## Debounce State Machine

State transitions must follow a deterministic timing model.

---

### Red Transition

Condition:

- value exceeds threshold

Rule:

- must persist for red_transition_seconds before transition

---

### Recovery Transition

Condition:

- value returns within acceptable range

Rule:

- must remain stable for recovery_seconds before transition

---

### State Progression

Transitions must follow:

GREEN → AMBER → RED  
RED → AMBER → GREEN

No direct jumps unless explicitly defined.

---

### Oscillation Prevention

Rules:

- transitions must not occur on transient spikes
- repeated boundary crossing must reset the timer

---

### Determinism Rule

Given identical time-series input:

- state transitions must occur at the same time
- transition outcomes must be identical across implementations

Precedence rule:

- hazard exception rules take precedence over debounce timers
- if no hazard applies, debounce rules determine transitions
---

## Structured Reason Schema

Evaluation reasons must follow a structured format.

---

### Reason Structure

Each reason must include:

- code
- message
- domain
- measured_value
- expected_range
- severity

Type constraints:

- code: stable uppercase identifier (example: HUMIDITY_HIGH)
- message: human-readable string
- domain: canonical signal path (<domain>.<signal>)
- measured_value: number | boolean | string | null
- expected_range: string | object
- severity: LOW | MEDIUM | HIGH | CRITICAL

---

### Example

reasons:
  - code: HUMIDITY_HIGH
    message: "Humidity above recommended range"
    domain: climate.humidity
    measured_value: 58
    expected_range: "42–50"
    severity: HIGH

  - code: UV_EXPOSURE_HIGH
    message: "Elevated UV exposure detected"
    domain: light.uv
    measured_value: present
    expected_range: "minimal"
    severity: HIGH

---

### Rules

- code must be stable and reusable
- domain must match environment model paths
- measured_value must reflect actual observed data
- expected_range must reflect asset requirements
- severity must align with risk levels
- reason list ordering must be deterministic (severity desc, then code lexical)

---

### Purpose

This structure ensures:

- UI consistency
- explainable Concierge responses
- structured reporting (insurance, audit)
- machine-readable reasoning
---
## Signal Naming Convention

All signals must use canonical paths aligned to environment domains.

---

### Format

<domain>.<signal>

---

### Examples

- climate.temperature
- climate.humidity
- light.lux
- light.uv
- air_quality.voc
- safety.leak

---

### Rules

- signal names must not be free-form
- UI, evaluation, and advisory must use the same naming
- reason schema must reference canonical paths

---

### Purpose

This prevents:

- naming drift
- inconsistent UI representation
- broken reasoning logic

---
## Timer Semantics

All debounce timing must follow a consistent time model.

---

### Time Source

The coordinator is the authoritative time source.

- timestamps must be based on coordinator cycle time
- wall-clock must not be inferred locally in components

---

### Timer Start

A timer begins when:

- a condition first enters a new state

---

### Timer Reset

The timer must reset if:

- the condition returns to the prior state before threshold is reached

---

### Example

Humidity rises above threshold:

- timer starts

Humidity briefly drops below threshold:

- timer resets

---

### Evaluation Granularity

Timers must be evaluated per coordinator cycle.

- partial cycles do not count
- consistent cycle boundaries required
- elapsed time is measured from cycle timestamps only

---

### Purpose

This ensures:

- consistent transition timing
- no race conditions
- deterministic behavior across systems

---
## Hazard Exception Rules

Certain signals may trigger immediate state transitions.

---

### Examples

- water leak detected
- extreme temperature spike
- fire/smoke conditions

---

### Rule

If hazard signal is detected:

- system may transition directly to RED
- debounce timing may be bypassed

---

### Requirements

- hazard signals must be explicitly defined
- behavior must be documented per signal
- transitions must remain explainable

Hazard signal registry:

- safety.leak = true -> immediate RED
- safety.smoke = true -> immediate RED
- safety.fire = true -> immediate RED

Rules:

- hazard registry entries must be versioned with model changes
- unknown hazard signals must not trigger immediate transitions

---

### Example

leak_detected = true → immediate RED

---

### Purpose

This ensures:

- safety-critical conditions are handled immediately
- deterministic behavior is preserved

---
## Runtime Projection Schema

The system must expose a consistent runtime projection for each asset.

---

### Structure

asset_projection:

  asset_id: string
  area_id: string | null
  evaluated_at: timestamp

  state:
    current: GREEN | AMBER | RED | UNCONFIGURED
    candidate: GREEN | AMBER | RED | UNCONFIGURED | null
    since: timestamp | null

  environment:
    reference: environment snapshot
    confidence: GOOD | PARTIAL | DEGRADED | STALE

  exposure:
    exposure_risk_level: NONE | LOW | MODERATE | HIGH
    directional_match: boolean
    effective_lux: number | null
    effective_uv: number | null

  reasons:
    structured_reason[]

  advisory:
    primary_message: string | null
    recommendations: string[]

---

### Rules

- all fields must exist
- missing values must be null
- structure must not vary across implementations
- evaluated_at must be ISO 8601 UTC timestamp (ending with Z)
- state.current must match current_state from evaluation output
- projection must be read-only and must not be persisted as source-of-truth data

---

### Purpose

This ensures:

- UI consistency
- Concierge consistency
- testability
- cross-repo compatibility

---

# FINAL PRINCIPLE

The asset defines intent.

The environment defines reality.

Evaluation determines condition.

Advisory suggests improvement.

No layer may take the role of another.