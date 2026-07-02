# Concierge Scope Contract

## Purpose

This contract defines the configuration and execution scope model for Concierge.

It formalizes three scopes:

- concierge-wide
- floor-wide
- room-wide

The goal is deterministic behavior with clear inheritance and override rules.

---

## Core Principle

Scope determines where a setting applies.

Priority determines which setting is effective.

For overlapping settings, the most specific valid scope wins.

---

## Scope Definitions

### Concierge-Wide

Applies to the entire home.

Examples:

- global context providers (weather, news, calendar)
- global quiet-hours policy
- capability enablement (AI, TTS, Music Assistant, Asset Intelligence connection)
- safety policy defaults

### Floor-Wide

Applies to all rooms on a floor.

Examples:

- thermostat/HVAC zone bindings
- floor media routing defaults
- floor speaker groups
- floor presence posture defaults

### Room-Wide

Applies only to one Home Assistant area.

Examples:

- room posture (day, night, sleep, away, nap)
- room speaker and voice assistant binding
- lights, shades, TV, sensors, and room-specific entities
- room persona and voice overrides

---

## Effective Resolution Order

For settings that exist at multiple scopes:

1. room-wide override
2. floor-wide default
3. concierge-wide default

If no valid value exists, Concierge must fail safely and explain what is missing.

---

## Communication Suppression Rules

### Quiet-Hours Policy

Quiet-hours is concierge-wide policy.

It defines default suppression windows and urgent bypass behavior.

### Room Posture Priority

Room posture remains room-wide and may increase suppression at any time.

This enables room-local behavior such as naps or early sleep without changing whole-home quiet-hours.

Rules:

- room posture may suppress info and attention interactions for that room
- room posture does not change concierge-wide quiet-hours for other rooms
- urgent handling must follow explicit urgent bypass policy

---

## Climate and Thermostat Boundaries

Thermostat and HVAC control is floor-wide by default.

Rationale:

- many homes have one thermostat per floor or zone
- room actions often map to shared floor equipment

Rules:

- thermostat targets should be configured at floor scope
- room-specific climate entities may override floor bindings when explicitly configured
- concierge-wide thermostat configuration is allowed only for true whole-home systems

---

## Music Assistant Scope Behavior

Music Assistant enablement is concierge-wide capability.

Operational routing should be floor-wide or room-wide.

Examples:

- concierge-wide: provider enabled, global safety policy for duck/pause/resume
- floor-wide: preferred group or default playback zone
- room-wide: preferred endpoint and room exceptions

Rules:

- Music Assistant must be treated as a capability provider, not only media_player control
- playback and TTS interaction must remain deterministic and explainable

---

## UI Model Requirement

Concierge UI must expose setup in three sections:

1. concierge-wide settings
2. floor-wide settings
3. room cards

Room pages must show inherited defaults and room overrides so effective behavior is visible.

---

## Final Principle

Concierge must behave as configured, not inferred.

Scope and precedence must be explicit, deterministic, and explainable.
