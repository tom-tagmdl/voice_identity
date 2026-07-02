# Service Contracts

## Purpose

Service Contracts define the API layer through which Concierge interacts with:

- UI
- integrations
- runtime execution
- external systems

All system interaction must occur through defined services.

Services provide the only supported mechanism for:

- reading state
- updating configuration
- executing actions
- retrieving interactions

---

## Core Principle

All system interaction flows through services.

UI does not execute logic.

Runtime does not bypass services.

---

## Service Design Rules

Services must:

- be deterministic
- have explicit inputs and outputs
- enforce validation before execution
- follow configuration-driven behavior

Services must not:

- contain hidden logic
- perform uncontrolled side effects
- bypass configuration or contracts

---

## Service Categories

Services are grouped into five categories:

1. Execution Services
2. Interaction Services
3. Signal Services
4. Configuration Services
5. Context Services

Scope model for configuration services:

- concierge-wide services define whole-home policy
- floor-wide services define floor defaults and shared infrastructure bindings
- room-wide services define local overrides

Effective resolution priority:

1. room-wide
2. floor-wide
3. concierge-wide

---

# 1. EXECUTION SERVICES

---

## Purpose

Execute actions within the home using predefined execution patterns.

---

## concierge.execute

Executes an action based on resolved intent.

Structure:

service: concierge.execute

input:
  target:
  area_id:
  composite_id:
  context:

behavior:

- resolve execution target from configuration
- apply execution hierarchy (scene → group → entity)
- execute via Home Assistant services

rules:

- must not perform runtime discovery
- must use preconfigured execution targets
- must execute in a single service call whenever possible

---

## concierge.execute_direct

Used when an explicit entity or scene is already resolved.

Structure:

service: concierge.execute_direct

input:
  entity_id:
  service:
  data:

rules:

- must bypass orchestration logic
- must only be used for direct execution paths (alias-first)

---

# 2. INTERACTION SERVICES

---

## Purpose

Provide access to interaction model for UI and voice integration.

---

## concierge.get_interactions

Returns active interactions for a room or composite.

input:
  area_id:
  composite_id:

output:
  interactions:

rules:

- must return only active interactions
- must respect expiration rules
- must be ordered by priority

---

## concierge.update_interaction

Updates interaction state.

input:
  interaction_id:
  state:

rules:

- must validate state transition
- must not persist invalid states

---

## concierge.clear_interaction

Removes an interaction.

input:
  interaction_id:

rules:

- must remove interaction from runtime
- must not affect underlying signals

---

# 3. SIGNAL SERVICES

---

## Purpose

Provide access to household state.

---

## concierge.get_signal

Returns a specific signal.

input:
  signal_type:

output:
  signal:

rules:

- must use Signal Contract
- must not infer state
- must return deterministic results

---

## concierge.get_signals

Returns all available signals.

input:
  area_id:
  composite_id:

output:
  signals:

rules:

- must respect room enablement
- must filter unavailable signals

---

# 4. CONFIGURATION SERVICES

---

## Purpose

Manage configuration through controlled API.

All configuration updates must occur through these services.

---

## concierge.update_room_config

Updates room configuration.

input:
  area_id:
  configuration:

rules:

- must validate structure
- must enforce schema rules
- must write to store only after validation
- may override floor defaults for that room
- must support room posture override for local calm behavior (including naps and early sleep)

---

## concierge.update_floor_config

Updates floor configuration.

input:
  floor_id:
  thermostat_entity_ids:
  climate_strategy:
  speaker_group_entity_ids:
  media_defaults:
  posture_default:

rules:

- must validate floor_id exists in Home Assistant floor registry
- floor thermostat/HVAC bindings are the default for rooms on that floor
- room config may override floor defaults
- must not mutate room definitions directly

---

## concierge.get_floor_config

Returns floor configuration and effective defaults.

input:
  floor_id:

output:
  floor_config:
  effective_defaults:

rules:

- must return deterministic values
- must include missing/invalid binding diagnostics

---

## concierge.update_composite_config

Updates composite room configuration.

input:
  composite_id:
  configuration:
  name:
  area_ids:

rules:

- must validate areas exist
- must enforce execution preferences
- must not conflict with room definitions
- must support merged room definitions where multiple areas resolve to one interaction context
- must support composite rename and membership edits in one deterministic update
- if area_ids becomes empty, composite must be dismantled and removed
- if area_ids removes some members, removed rooms must return to standalone projection
- composite inventory and selectors must be recalculated from remaining members only

---

## concierge.sync_composites

Validates and rebuilds merged room runtime projections.

input:
  add_missing:
  remove_invalid:

output:
  composites:
  validation_errors:

rules:

- must validate every member area exists
- must validate that voice invocation from any member area resolves to the same composite context
- must reject ambiguous membership unless explicitly allowed by policy
- must clear stale device references for rooms no longer in each composite

---

## concierge.update_global_context

Updates global context usage.

input:
  context_type:
  enabled:
  options:

rules:

- must not modify underlying providers
- must only affect usage

---

## concierge.update_global_policy

Updates concierge-wide policy.

input:
  quiet_hours:
  urgent_bypass:
  capability_toggles:

rules:

- quiet-hours policy is concierge-wide default
- room posture may increase suppression at room scope
- updates must validate policy consistency before persisting

---

## concierge.update_execution_preferences

Defines execution behavior.

input:
  area_id or composite_id:
  preferences:

rules:

- must enforce execution hierarchy
- must validate scenes and groups exist

---

## concierge.update_music_routing

Updates Music Assistant routing policy at concierge, floor, or room scope.

input:
  scope:
  scope_id:
  routing:
  tts_behavior:

rules:

- concierge scope enables capability and global safety policy
- floor scope defines default routing/group behavior
- room scope defines endpoint overrides
- TTS duck/pause/resume behavior must be deterministic

---

# 5. CONTEXT SERVICES

---

## Purpose

Provide access to global context (weather, news, email, etc.).

---

## concierge.get_context

Retrieves a global context item.

input:
  context_type:

output:
  context:

rules:

- must use Global Context Contract
- must not generate context independently

---

## concierge.get_summary

Returns a combined summary.

input:
  area_id:
  include_signals:
  include_context:

output:
  summary:

rules:

- may use AI for summarization (if allowed)
- must remain grounded in real data

---

# VOICE INTEGRATION FLOW

---

Voice processing must follow:

1. Assist resolves entity or alias
2. If match:
   → concierge.execute_direct

3. If no match:
   → concierge.execute (orchestrated)

rules:

- must prefer direct execution
- must minimize latency
- must remain deterministic

---

# UI INTEGRATION FLOW

---

UI must:

- call services for all actions
- never invoke execution directly
- never modify store directly

Example:

User clicks action →

- UI calls concierge.execute
- runtime performs action
- UI updates via get_interactions

---

# AI INTEGRATION

---

AI may be invoked only through services.

AI usage must be:

- optional
- bounded
- controlled by global configuration

AI must not:

- directly call execution services
- bypass validation
- modify system state

---

# VALIDATION REQUIREMENTS

---

All services must:

- validate inputs
- validate entity existence
- validate configuration integrity

Invalid requests must:

- be rejected
- return clear error messages

---

# PERFORMANCE REQUIREMENTS

---

Services must:

- use precomputed configuration
- avoid runtime discovery
- execute in a single call when possible

The system must not:

- introduce loops in execution path
- perform template processing at runtime

---

# FAILURE HANDLING

---

If service fails:

- return clear response
- do not retry indefinitely
- do not produce partial execution

Fallback must:

- follow execution hierarchy
- remain deterministic

---

# SECURITY RULES

---

Services must:

- respect integration boundaries
- prevent unauthorized access
- protect sensitive data

Sensitive configuration must not be exposed through service outputs.

---
# CAPABILITY MODEL

---

## Purpose

Defines callable system capabilities exposed by Concierge.

Capabilities represent:

- actions (play music)
- informational queries (air quality)
- advisory responses (why something happened)

---

## Structure

capabilities:

  <capability_id>:
    type:
    domain:
    requires_context:

Example:

capabilities:

  speak_air_quality:
    type: informational

  play_music:
    type: action

  explain_music_choice:
    type: advisory

---

## Types

- action
- informational
- advisory

---

## Rules

Capabilities must:

- map to a service or execution path
- be deterministic
- be reusable across voice and UI

Capabilities must not:

- embed logic in UI or automations
- duplicate execution paths

---

# FINAL PRINCIPLE

Services define how the system is used.

All behavior must pass through:

- explicit contracts
- validated inputs
- deterministic execution

The system must never operate outside of defined service boundaries.