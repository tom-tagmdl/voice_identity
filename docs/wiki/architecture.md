# Architecture

## Platform Role

Voice Identity is the HTBW service that answers who is interacting, using privacy-safe outputs and clear subsystem boundaries.

## Standalone Repository Boundary

Voice Identity owns:

- speaker fingerprint generation
- fingerprint lifecycle and revision handling
- attribution evidence projection
- identity context projection
- compatibility/readiness health surfaces

Voice Identity does not own Concierge orchestration, permissions, room context, or enrollment UI.

## Concierge Boundary

Concierge consumes safe public outputs only and does not embed Voice Identity internals.

## Ownership Model

- Voice Identity: identity artifact lifecycle and evidence services
- Concierge: context, policy, orchestration, and user experience

## Local-First Design

- Local-first architecture is an explicit ADR requirement.
- Cloud dependency is not required for baseline operation.

## Release Readiness Status

Release readiness is governed by VI-129 and validated by test suites, including dependency, compatibility, performance, resiliency, and release-readiness gates.
