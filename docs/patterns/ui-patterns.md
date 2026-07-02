# UI Patterns

## Purpose

UI Patterns define how the system presents information and interacts with the user.

They ensure all interfaces are:

- consistent
- predictable
- explainable
- aligned with Home Assistant standards
- derived from system configuration and runtime models

---

## Core Principle

The user interface must feel native to Home Assistant while delivering a more disciplined and predictable experience.

---

## Foundational Rule

The UI is a projection of configuration and runtime state.

The UI must not:

- execute system logic directly
- act as a source of truth
- store independent state

---

## System Boundary (Critical)

The system is divided into:

### Global Configuration

- AI providers
- external integrations (M365, etc.)
- authentication and system settings

Not exposed in main UI.

---

### Operational UI

- rooms
- interactions
- signals
- global context usage
- scene exposure and configuration

These are Home Assistant-native sections and flows, not a separate UI shell.
They should be implemented with native panels, cards, dialogs, and selectors so the experience remains indistinguishable from Home Assistant.

---

## Foundations

The UI must always:

- reflect system state clearly
- preserve user context
- avoid unnecessary complexity
- prioritize understanding over control

---

# 1. Navigation Patterns

## Breadcrumb Navigation

Breadcrumbs must:

- always be visible
- reflect the user's entry path
- be fully clickable
- not force hierarchy

Example:

Home > Living Room > Painting  
Alerts > Painting  
Documents > Appraisal  

---

## Back Navigation

Back navigation must restore:

- selected tab
- filters
- scroll position (best effort)

---

## Cross-Domain Navigation

Cross-cutting views must remain independent.

Examples:

- Alerts
- Documents
- History
- Interactions

Rules:

- do not force hierarchy
- preserve original context

---

# 2. Information Hierarchy

Every screen must follow:

1. Status
2. Context
3. Explanation
4. Actions
5. History

---

## Example: Room Dashboard

Status:
- room state
- confidence

Context:
- environment summary
- global context availability

Explanation:
- primary issue or insight

Actions:
- available interactions

History:
- optional drill-down

---

# 3. Progressive Disclosure

The UI must reveal information progressively.

Rules:

- show high-level state first
- allow drill-down for detail
- never overwhelm the user

---

# 4. State Visibility and Explainability

The UI must always show:

- what is happening
- why it is happening
- confidence in the result

---

# 5. Empty State Handling

The UI must never show unexplained gaps.

When data is missing:

- explain why
- guide resolution

---

# 6. Action Patterns

## Core Rule

UI actions do NOT execute system behavior directly.

UI must:

- call services
- reflect results

---

## Buttons

Buttons must:

- follow HA standards
- provide immediate feedback
- reflect loading/disabled state

---

## Confirmation

Required for:

- destructive actions
- major configuration changes

---

# 7. Dialog (Popup) Patterns

Dialogs must:

- use HA native components
- be consistent in layout

---

# 8. Iconography

### Layer 1: Native

- entities
- sensors

### Layer 2: System

- signals
- context
- interactions

---

# 9. Color Semantics

- Blue → context  
- Green → normal  
- Amber → warning  
- Red → critical  
- Gray → unknown  

---

# 10. Layout Patterns

Structure:

- top → summary
- middle → context and explanation
- bottom → detail and history

---

# 11. Consistency Rules

The same concept must appear identically everywhere.

---

# 12. State Synchronization

UI must:

- read from runtime models (coordinator/store)
- not compute state
- not simulate final state

---

# 13. Voice and UI Alignment

Voice and UI must match:

- terminology
- explanation
- behavior

---

# 14. Performance and Responsiveness

UI must:

- feel immediate
- not perform heavy logic
- rely on precomputed data

---

# 15. Interaction Feedback and Perceived Performance

## Rule

Every user action must produce immediate visible feedback.

### Immediate Feedback

- highlight selection
- update state instantly

### In-Progress Feedback

- spinner
- disabled state

### Completion Feedback

- state update
- confirmation

---

# 16. Interaction Panel Pattern (NEW)

## Purpose

Provides a unified surface for:

- signals
- context
- actions
- workflows

---

## Structure

Room Interaction Panel:

- Context (weather, news, email)
- Signals (laundry, calendar)
- Actions (available controls)
- Workflows (setup, guided flows)

---

## Rules

- must display only active interactions
- must not store independent state
- must reflect interaction model

---

# 17. Scene and Alias Visibility (NEW)

Scenes must be visible and configurable.

UI must show:

- scene name
- aliases (from Home Assistant)
- enable/disable for room
- composite inclusion

---

## Rules

- aliases are source-of-truth (HA)
- UI may allow editing aliases
- UI must not duplicate phrase systems

---

# 18. Global Context UI Pattern (NEW)

Global context must be configurable in UI.

Examples:

- weather
- news
- calendar
- email

---

## Rules

- enable/disable per context
- configure summarization behavior
- support per-room projection

---

# 19. Configuration Projection Rule (CRITICAL)

UI must always reflect:

- configuration (store)
- runtime state (models)

UI must never:

- be the source of configuration truth
- modify behavior outside services

---

## Flow

UI → service call → validation → store update → runtime update → UI refresh

---

# 20. Optimistic vs Confirmed Updates

Optimistic:

- safe UI-only updates

Confirmed:

- required for state changes and execution

---

# 21. Relationship to Runtime

UI must:

- call Concierge services
- render interaction model
- reflect execution results

UI must not:

- directly manipulate entities
- bypass execution patterns
- perform orchestration

---

# 22. User Experience Principles

The UI must always:

- prioritize clarity
- minimize effort
- build trust
- avoid noise

---

# 23. Merged Room UI Pattern (NEW)

Merged room (composite) creation must be managed from the main Concierge UI.

Required UI flow:

1. user enters merge mode from main screen
2. user provides merged room name
3. user selects member rooms using room-card checkboxes
4. user confirms merge

Rules:

- merge mode must only allow selecting rooms on the same floor
- cross-floor selection must be rejected with clear inline feedback
- merge confirmation must show selected rooms and floor before save

---

## Main Screen Projection Rules

After merge succeeds:

- member room tiles must be replaced by one composite tile
- composite tile title must use the merged room name
- composite tile must list member room names for quick reference
- member room tiles must not remain visible as primary cards in that view

If merge is removed:

- composite tile must be removed
- member room tiles must return

---

## Composite Edit and Unmerge Pattern

Composite tiles must expose an Edit action from the main Concierge UI.

Edit UI must include:

- editable composite name
- checklist of current member rooms
- save action with validation feedback

Rules:

- unchecking one room removes that room from the composite
- if one room is removed, that room tile must reappear in the main screen while remaining members stay as a composite tile
- if all rooms are removed, the composite must be dismantled and removed from the main screen
- when dismantled, all individual room tiles must return

Composite rename rules:

- rename must happen in the same Edit flow
- updated name must appear on the composite tile immediately after confirmed save

---

## Composite Detail Configuration Rules

Selecting a composite tile must open composite detail configuration.

Composite device selectors must be built from the union of devices across all member rooms.

Rules:

- no duplicate entities in selector lists
- ordering must be deterministic
- unavailable entities must be visibly marked

---

# 24. Setup Mode: Rooms And People (NEW)

The main setup experience must allow choosing setup intent first.

Required setup entry choices:

- Rooms And Areas
- People

Rules:

- selection must be explicit before entering definitions
- each setup path must keep its own forms, validation, and guidance
- switching paths must preserve unsaved work warning behavior

---

## Rooms And Areas Setup Path

The rooms path configures:

- rooms
- merged spaces
- controllable device scope per room and space

This path remains the foundation for deterministic local-first resolution.

---

## People Setup Path

The people path must use Home Assistant person entities as the starting point.

People setup configures:

- BLE proximity device links such as iPhone and watch sources
- Aqara room presence device links used as supporting context
- optional voice enrollment status

People setup must not duplicate person identity records outside Home Assistant references.

People setup must treat device links as editable parts of the person definition.


---

# 25. People Tiles Pattern (NEW)

People should be represented in tiles, similar to room tiles.

People tiles should show:

- linked BLE proximity devices
- linked room presence devices

Tile actions should include:

- link or unlink devices

Rules:

- people tiles are projections of model state
- tile actions must call services
- no direct state mutation in UI

---

# 26. Mid-Conversation Style Adjustment Surface (NEW)

The UI should expose recent style adjustments captured during conversation.

Examples:

- switched to brief responses
- reduced follow-up prompts
- enabled more detail

Rules:

- each adjustment must be explainable in plain language
- users must be able to keep, undo, or reset adjustments
- saved adjustments must update person profile deterministically
- selections must persist through services, not direct UI mutation

---

# 27. Person Enrollment Detail Pattern (NEW)

The person detail screen must show enrollment and device-binding state.

Required detail sections:

- identity overview
- linked BLE proximity devices
- linked room presence devices
- voice enrollment status
- interaction style summary
- recent corrections and adjustments

Rules:

- device links must be editable from the detail screen
- voice enrollment may be enabled or deferred independently
- details must remain human understandable and plain language
- selections must persist through services, not direct UI mutation

---

# Final Principle

The UI is not a control surface.

It is a window into a system that already knows what to do.

The user should feel:

- confident
- informed
- in control—without needing to manage complexity
