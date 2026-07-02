# Concierge Global Configuration Contract

## Purpose

The Concierge Global Configuration Contract defines system-wide settings for Concierge.

It governs:

- provider enablement and connectivity
- global communication policy
- default behavior used when floor or room overrides are not configured

Global configuration is foundational and must remain separate from floor and room configuration.

---

## Core Principle

Global config defines defaults and policy.

Floor and room config define local behavior.

Global config must not remove room-level control of posture.

---

## Scope Boundary

Global configuration applies to:

- concierge-wide capability toggles (AI, TTS, Music Assistant, Asset Intelligence connectivity)
- whole-home context provider selection (weather, news, calendar, alarm)
- quiet-hours defaults
- urgent bypass policy

Global configuration does not own:

- room posture
- room entity bindings
- floor thermostat/HVAC routing details

---

## Global Configuration Structure

concierge_global_config:
  providers:
    context:
      weather:
      news:
      calendar:
      alarm_status:
    ai:
      enabled:
      local_first:
      provider:
      model:
    tts:
      enabled:
      provider:
      default_voice:
    music_assistant:
      enabled:
      provider:
      tts_ducking:
      tts_resume:
  communication:
    quiet_hours:
      enabled:
      start:
      end:
      timezone:
    urgent_bypass:
      enabled:
      allow_voice:
  defaults:
    posture_default:
    summary_style:

---

## Quiet-Hours Policy

Quiet-hours is concierge-wide policy.

Rules:

- quiet-hours defines the default suppression window across the home
- quiet-hours does not force room posture values
- room posture may further suppress interactions for one room (nap or early sleep)
- urgent behavior must follow urgent_bypass policy

---

## Room Posture Interaction

Room posture remains room-scoped.

Rules:

- room posture may suppress info and attention for that room at any time
- room posture does not alter global quiet-hours for other rooms
- effective communication behavior must be explainable as:
  room posture override -> floor default -> global quiet-hours default

---

## Thermostat and HVAC Defaults

Thermostat and HVAC zone routing should default to floor scope.

Global config may define policy but not specific per-floor entity bindings.

Examples of allowed global policy:

- allow proactive climate recommendations
- allow climate actions during quiet-hours (true/false)

Examples of floor-owned configuration:

- floor thermostat entity_id
- floor climate strategy defaults

---

## Music Assistant Configuration

Music Assistant is a concierge-wide capability toggle with local routing behavior.

Rules:

- enabling Music Assistant is global
- floor/room bindings decide where playback and TTS route
- Music Assistant must be treated as a capability provider, not only media_player passthrough
- pause/duck/resume behavior around TTS must be deterministic

---

## Validation Rules

Global config updates must:

- validate provider availability
- reject unsupported provider values
- reject invalid quiet-hours windows
- reject conflicting urgent_bypass combinations

Invalid updates must not partially apply.

---

## Final Principle

Global configuration sets whole-home policy.

Room posture still controls local calm behavior.

This separation is required for deterministic and user-respectful interaction behavior.