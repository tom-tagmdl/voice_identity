# Homes That Behave Well

Homes That Behave Well is the authoritative platform specification for building calm, deterministic, explainable, and trustworthy Home Assistant-based homes.

This repository is the source of truth for how the Homes Platform is designed, how responsibilities are divided, and how integrations must behave when working together.

It governs the shared rules and contracts used across:

- Asset Intelligence
- Concierge
- Future platform integrations such as security, energy, presence, and additional intelligence layers

---

## What This Repository Is

This repository defines the platform itself.

It contains the authoritative:

- philosophy
- architecture
- contracts
- models
- patterns
- cross-repo behavioral rules

These documents are intended to prevent architectural drift and ensure all implementations remain aligned as the platform expands.

---

## What This Repository Governs

Homes That Behave Well defines:

- platform philosophy and behavioral expectations
- architectural boundaries between integrations
- service interaction rules
- runtime and configuration models
- interaction and execution patterns
- AI usage boundaries
- performance and determinism requirements
- Home Assistant-native implementation standards

This repository does not execute runtime logic. It defines the rules that runtime implementations must follow.

---

## Platform Model

The platform is built from independent integrations with strict responsibilities.

| Component | Responsibility |
|------|----------------|
| Asset Intelligence | System of record, environmental evaluation, validation, persistence, advisories |
| Concierge | Orchestration, interaction, communication, room-aware context delivery, capability routing |
| Homes That Behave Well | Platform philosophy, architecture, contracts, models, patterns, governance |

---

## Core Principles

Homes in this platform must be:

- Calm: no unnecessary interruptions, noise, or repetition
- Predictable: the same input leads to the same outcome
- Explainable: every action and response has a clear reason
- Deterministic: execution paths are defined in advance
- Local-first: Home Assistant-native capability is preferred whenever possible
- Progressively intelligent: new integrations extend understanding without increasing chaos

---

## Responsibility Boundaries

The platform depends on strict separation of concerns.

- Concierge never owns domain data, evaluation logic, or system-of-record persistence.
- Asset Intelligence never owns interaction, orchestration, or communication behavior.
- Homes That Behave Well defines the contracts and rules both must follow.

This separation is a platform guarantee, not a style preference.

---

## AI Position

AI is optional, bounded, and subordinate to deterministic system behavior.

Rules:

- AI never mutates system state directly
- AI may assist with summarization, explanation, and bounded recommendations
- All state changes must go through validated services and defined contracts
- AI outputs must remain explainable, auditable, and grounded in system data

AI may improve delivery. It must not redefine truth or execution.

---

## Home Assistant Alignment

All downstream implementations are expected to remain native to Home Assistant.

This includes:

- config flow and options flow patterns
- service registration and validation
- entity and device registry usage
- native dialogs, selectors, and UI behaviors
- HACS-compliant repository and release practices

Homes That Behave Well does not replace Home Assistant standards. It layers platform rules on top of them.

---

## How To Read This Repository

Recommended reading order:

1. Philosophy
2. Architecture
3. Contracts
4. Models
5. Patterns

Suggested entry points:

- [docs/philosophy/homes-that-behave-well.md](docs/philosophy/homes-that-behave-well.md)
- [docs/architecture/canonical-architecture.md](docs/architecture/canonical-architecture.md)
- [docs/contracts/concierge-contract.md](docs/contracts/concierge-contract.md)
- [docs/contracts/asset-intelligence-contract.md](docs/contracts/asset-intelligence-contract.md)

---

## Repository Structure

Top-level structure:

- `docs/philosophy/` — why the system behaves the way it does
- `docs/architecture/` — canonical structure, runtime layering, and system flow
- `docs/contracts/` — boundaries, service surfaces, and platform obligations
- `docs/models/` — data and runtime representations
- `docs/patterns/` — implementation rules for execution, interaction, messaging, UI, and configuration
- `examples/` — scenarios and interaction flows used to illustrate intended behavior

---

## How Downstream Repositories Use This

This repository is designed to be used alongside implementation repositories such as Asset Intelligence and Concierge.

It is used to:

- ground implementation decisions in shared platform rules
- keep cross-repo behavior synchronized
- guide Copilot and human development work
- reduce ambiguity during feature design and refactoring
- ensure future integrations inherit consistent behavior

When patterns evolve in implementation, those changes should be reflected here so the platform remains coherent.

---

## Governance Rule

Contracts and architecture in this repository take precedence over downstream reinterpretation.

If an implementation introduces a new pattern, boundary, or capability model that affects more than one integration, this repository must be updated so that the change becomes part of the shared platform definition.

This repository exists to keep the platform aligned as it grows.

---

## Design Goal

This platform is not conventional automation.

It is a structured, deterministic, decision-support system for the home.

The goal is not merely to automate devices.

The goal is to create a home that understands context, behaves predictably, and explains itself clearly.