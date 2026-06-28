# Concierge Global Configuration Contract

## Purpose

The Concierge Global Configuration defines system-level settings that control how Concierge operates across the entire home.

This configuration governs:

- AI provider configuration
- voice and speech behavior
- system-wide execution rules
- external integration connections

Global Configuration is foundational and must be separated from room-level and interaction-level configuration.

---

## Core Principle

Global Configuration defines how the system operates.

Room and UI configuration define how the system behaves.

---

## Scope

Global Configuration applies to:

- all rooms
- all interactions
- all execution paths

It is not scoped to any individual room or user interaction.

---

## Configuration Layers

Global Configuration consists of three layers:

1. System Providers
2. Behavior Rules
3. Integration Connections

---

# 1. SYSTEM PROVIDERS

---

## Purpose

Defines the providers used for AI and voice capabilities.

---
# IDENTITY AND PERSONA CONFIGURATION

---

## Purpose

Defines how Concierge adapts interaction behavior and content presentation based on the identity of the user.

This includes:

- voice selection
- verbosity and tone
- interaction style
- AI usage preferences
- content selection and description style

Identity allows Concierge to deliver the **same system truth** in a way that is appropriate for the person interacting with it.

---

## Core Principle

Identity affects **how information is delivered**, not **what actions are executed**.

---

## Structure

```
identity:

  enabled:

  default_profile:
    persona:
    tts_voice:
    verbosity:
    allow_ai:

    content_profile:
      type:
      detail_level:

  profiles:

    <person_id>:
      name:

      persona:
      tts_voice:
      verbosity:
      allow_ai:

      content_profile:
        type:
        detail_level:
```

---

## Field Definitions

### enabled

Determines whether identity-aware behavior is active.

When disabled:

* default profile is always used
* no identity-based variation occurs

---

### default\_profile

Fallback profile used when identity is unknown or cannot be resolved.

---

### profiles

Defines per-person overrides.

Example:

```
profiles:

  tom:
    name: Tom

    persona: concise
    tts_voice: voice_tom
    verbosity: minimal
    allow_ai: true

    content_profile:
      type: technical
      detail_level: high

  guest:
    name: Guest

    persona: conversational
    verbosity: standard
    allow_ai: true

    content_profile:
      type: general
      detail_level: medium
```

---

### persona

Defines communication style.

Examples:

- concise
- conversational
- advisory
- technical

---

### tts\_voice

Voice assigned to the user.

Must correspond to a valid configured TTS voice.

---

### verbosity

Controls response length and detail.

Examples:

- minimal → brief, direct
- standard → balanced
- detailed → expanded explanation

---

### allow\_ai

Determines whether AI may be used for this user.

Rules:

- must follow global AI constraints
- must not enable AI-driven execution

---

## Content Profile

Defines how information is selected and presented across integrations.

---

### content\_profile.type

Determines which description variant should be used.

Examples:

- general
- technical
- advisory

---

### content\_profile.detail\_level

Controls how much detail should be presented.

Examples:

- low
- medium
- high

---

## Content Selection Behavior

When presenting information:

1. resolve identity (if available)
2. select profile:
  - room override (if present)
  - user profile
  - default profile
3. determine content\_profile
4. request matching content variant from integration
5. apply persona and verbosity

---

## Rules

Identity behavior must:

- be deterministic when identity is known
- fall back to default when unknown
- apply consistently across voice and UI

Content selection must:

- use integration-provided variants
- not alter underlying system state
- remain consistent across interactions

---

## Constraints

Identity must not:

- influence execution decisions
- override execution patterns
- introduce ambiguity in system behavior

Content profiles must not:

- introduce alternate logic
- modify signals or asset state
- fabricate or infer missing data

---

## System Behavior Rules

The system must:

- apply identity consistently across sessions
- deliver the same truth with different presentation styles
- maintain alignment between voice and UI

The system must not:

- create divergent system behaviors for different users
- allow identity to change what the system does

---

## Final Principle

Identity personalization changes the experience, not the outcome.

The system must always do the same thing.

It may explain it differently.

---
## AI Configuration

AI must be explicitly configured and must follow local-first execution rules.

Structure:

ai:
  enabled:
  local_first:
  action_llm:
    provider:
    model:
    endpoint:
    api_key:
    timeout:
  tts_llm:
    provider:
    model:
    voice:
    endpoint:

---

## Rules

AI must:

- be optional and configurable
- operate only when deterministic execution is not sufficient
- never be required for core system functionality

AI must not:

- directly execute actions
- determine execution strategy
- override system-defined behavior

---

## TTS Configuration

Defines text-to-speech behavior.

Structure:

tts:
  provider:
  default_voice:
  volume_profile:

Rules:

- must support Home Assistant native TTS when available
- must not delay execution
- must integrate with audio routing model

---

# 2. BEHAVIOR RULES

---

## Purpose

Defines system-wide behavior constraints and policies.

---

## Execution Behavior

Structure:

behavior:
  prefer_local_execution:
  require_deterministic_execution:
  allow_ai_for:
    - summarization
    - disambiguation
    - recommendations
  block_ai_for:
    - execution
    - device_control
    - state_interpretation

---

## Rules

The system must:

- prefer local execution over external calls
- remain deterministic for all actions
- execute immediately once intent is resolved

The system must not:

- depend on AI for execution decisions
- introduce latency due to unnecessary processing

---
# AUDIO BEHAVIOR CONFIGURATION

---

## Purpose

Defines how Concierge manages audio during voice interactions, including:

- text-to-speech volume
- media ducking behavior
- post-interaction restoration

This configuration ensures consistent and predictable audio behavior across the home.

---

## Structure

audio_behavior:

  tts:
    default_volume:
    max_volume:

  ducking:
    enabled:
    duck_level:
    restore_after:

---

## Field Definitions

### tts.default_volume

The default volume used for voice responses when no room override is defined.

---

### tts.max_volume

Maximum allowed TTS volume for safety and consistency.

---

### ducking.enabled

Controls whether active media should be reduced (ducked) during TTS playback.

---

### ducking.duck_level

The volume level to reduce active media to during TTS.

Example:

0.3 → audio reduced to 30% of original level

---

### ducking.restore_after

Determines whether original media levels should be restored after TTS completes.

---

## Rules

Audio behavior must:

- be deterministic
- be applied consistently across all interactions
- not delay execution

The system must:

- capture current media state before modification
- restore previous state if configured

The system must not:

- guess or infer media state
- rely on external history systems

---

## Relationship to Execution

Audio behavior is applied during execution and follows the same principles:

- preconfigured
- immediate
- non-blocking

---

## Override Model

Global audio behavior defines defaults.

Rooms may override these values through room configuration.

The system must always apply:

1. room override (if present)
2. global configuration (fallback)

---
# MEDIA PROVIDER CONFIGURATION

---

## Purpose

Defines how Concierge enables and uses media capabilities that may depend on Music Assistant.

---

## Structure

media:

  provider:
    type:
  use_music_assistant:

---

## Values

type:

- auto
- music_assistant
- home_assistant

---

## Behavior

auto:

- detect at startup or configuration refresh whether Music Assistant is installed
- if installed and explicitly enabled, expose Music Assistant-dependent capabilities
- otherwise use Home Assistant media_player capabilities only

music_assistant:

- require Music Assistant to be installed and explicitly enabled
- expose Music Assistant-dependent capabilities only when both conditions are true

home_assistant:

- use native HA media_player only
- do not expose Music Assistant-dependent capabilities

---

## Rules

- provider capability enablement must be determined at startup or configuration refresh
- runtime must not switch providers dynamically
- Music Assistant usage must require explicit opt-in
- execution must remain deterministic

---

## Fallback

If selected provider is unavailable:

- disable Music Assistant-dependent capabilities
- fallback to home_assistant capability set
- do not fail baseline media execution

---
## AI Fallback Rules

Structure:

fallback:
  allow_llm_fallback:
  require_confirmation_for_actions:

Rules:

- fallback must be explicit
- user safety must be preserved
- all AI-driven actions must be explainable

---

# 3. INTEGRATION CONNECTIONS

---

## Purpose

Defines external system connections and authentication.

Examples:

- Microsoft 365
- weather providers
- news providers
- third-party APIs

---

## Connection Model

Structure:

connections:
  microsoft_365:
    connected:
    permissions:
  weather:
    provider:
  news:
    provider:

---

## Rules

Connections must:

- be configured behind the integration settings (gear icon)
- separate authentication from usage
- expose capabilities to Concierge via contracts

Connections must not:

- expose credentials in UI
- bypass integration boundaries
- embed logic within Concierge

---

# CONFIGURATION ACCESS MODEL

---

## UI Separation

Global Configuration must be accessed via:

- Home Assistant integration options (gear icon)

It must not be exposed in:

- room configuration UI
- interaction panels
- end-user dashboards

---

## Usage vs Configuration

Rules:

- configuration defines system capability
- UI defines how capability is used

Example:

Connecting Microsoft 365 → configuration  
Enabling calendar in Concierge → UI  

---

# RELATIONSHIP TO OTHER MODELS

---

## Global Context

Global Configuration enables Global Context sources.

It does not define how they are used.

---

## Signals

Global Configuration enables integrations that provide signals.

It does not define signal state or behavior.

---

## Execution

Global Configuration defines rules governing execution.

Execution Patterns define how actions occur.

---

## Concierge

Concierge consumes Global Configuration but does not modify it.

---

# FAILURE HANDLING

---

If configuration is incomplete:

- system must continue operating in local-only mode
- AI capabilities must be disabled
- execution must remain deterministic

The system must never:

- fail completely due to missing configuration
- attempt unsafe fallback behavior

---

# SECURITY RULES

---

Global Configuration must:

- protect credentials and API keys
- ensure secure communication with external services
- restrict unauthorized access

Sensitive data must never be exposed in:

- UI panels
- interaction models
- logs visible to users

---

# SYSTEM BEHAVIOR RULES

---

The system must:

- remain local-first
- be deterministic by default
- allow controlled extensibility via providers

The system must not:

- rely on external systems for core functionality
- introduce nondeterministic behavior
- blur separation between configuration and execution

---

# FINAL PRINCIPLE

Global Configuration defines the foundation of the system.

It enables capability, but does not define experience.

Concierge uses this foundation to deliver a consistent, reliable, and context-aware interaction model across the home.