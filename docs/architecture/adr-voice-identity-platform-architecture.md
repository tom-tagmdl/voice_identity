# ADR: Voice Identity Platform Architecture

## 1. Status

ACCEPTED

## 2. Purpose

Voice Identity architecture has completed foundational design work.

This ADR records and ratifies the approved architecture.

The purpose of this ADR is to:

- document architectural decisions
- preserve reasoning
- prevent architectural drift
- provide future implementation guidance
- define platform boundaries

This ADR is the architecture-of-record.

## 3. Background

Voice Identity began as voice enrollment functionality inside Concierge.

Architecture analysis determined that the following represent a separate bounded domain:

- voiceprint generation
- voiceprint lifecycle management
- artifact governance
- future speaker attribution
- identity confidence
- identity resolution

Voice Identity therefore became a first-class HTBW platform service.

## 4. Platform Position

Approved HTBW platform model:

- Foundation: What is true?
- Asset Intelligence: What matters?
- Voice Identity: Who is interacting?
- Concierge: What should happen?

Voice Identity is a peer platform service and not a Concierge subsystem.

## 5. Approved Architectural Decisions

### Decision 1: Voice Identity is a standalone HTBW platform service

Accepted.

Rationale:

- bounded domain separation
- independent deployment
- independent lifecycle
- cleaner HACS model
- cleaner privacy model

### Decision 2: Voice Identity owns Voiceprints

Accepted.

Voice Identity owns:

- Voiceprint generation
- Voiceprint lifecycle
- Voiceprint storage
- Voiceprint revisions
- Voiceprint migrations
- Voiceprint deletion

### Decision 3: Concierge consumes Voice Identity

Accepted.

Concierge owns:

- people
- permissions
- context
- coordinator
- activities
- conversations
- intent routing
- enrollment user experience

Concierge does not own:

- vectors
- embeddings
- attribution logic
- Voiceprint artifacts
- model lifecycle

### Decision 4: Voiceprint is the canonical identity artifact

Accepted.

Voiceprint consists of:

- stable voiceprint_ref
- immutable revisions
- quality metadata
- lifecycle metadata
- consent metadata
- provider-owned identity representation

Voiceprints are durable.

Enrollment recordings are temporary.

### Decision 5: Technology direction

Accepted.

Voiceprint generation:

- ECAPA-class speaker embeddings

Deployment:

- ONNX runtime strategy

Runtime execution:

- local-first sidecar architecture

Concierge remains implementation-agnostic.

### Decision 6: Provider-owned storage

Accepted.

Voice Identity stores:

- Voiceprint artifacts
- encrypted representation data
- model metadata
- lifecycle metadata

Concierge stores only:

- voiceprint_ref
- safe metadata
- status
- quality summary

### Decision 7: Privacy boundary

Accepted.

Never exposed:

- vectors
- embeddings
- raw audio
- artifact payloads
- storage paths
- model internals
- attribution internals

Only safe metadata crosses the service boundary.

### Decision 8: Identity Context is the canonical output

Accepted.

Voice Identity ultimately produces Identity Context.

Identity Context consumers:

- Concierge
- Coordinator
- future HTBW services

Coordinator consumes Identity Context.

Coordinator does not consume Voice Identity internals.

## 6. Voiceprint Architecture Summary

Voiceprint architecture includes:

- stable lineage identifier
- immutable revision model
- encrypted internal representation
- quality scoring
- lifecycle state
- consent binding
- migration support

Revision philosophy:

- voiceprint_ref remains stable
- voiceprint_revision increments
- only one active revision exists at a time

## 7. Service Architecture Summary

Approved public capability model:

Voiceprint Operations:

- GenerateVoiceprint
- GetVoiceprintStatus
- GetVoiceprintMetadata
- RegenerateVoiceprint
- DeleteVoiceprint

Attribution Operations:

- AttributeSpeaker
- ValidateAttributionRequest
- GetAttributionAvailability

Health Operations:

- GetServiceHealth
- GetProviderHealth
- GetModelHealth
- GetStorageHealth

Capability Operations:

- GetSupportedModels
- GetContractVersions
- GetSchemaVersions
- GetFeatureAvailability

## 8. Concierge Integration Summary

Approved integration model:

- Voice Identity is optional
- Concierge must continue operating when Voice Identity is unavailable, unhealthy, disconnected, or incompatible
- Voice Identity enhances Concierge
- Voice Identity does not replace Concierge

Approved Identity Context model:

- identity_status
- identity_source
- person_id
- voiceprint_ref
- voiceprint_revision
- speaker_match_confidence
- confidence_band
- reason_code_safe

## 9. Approved Principles

1. Context Before Intent
2. Identity Before Authorization
3. Voiceprints Are Durable Artifacts
4. Enrollment Recordings Are Temporary
5. Concierge Consumes Identity
6. Voice Identity Owns Identity
7. Local-First By Default
8. Privacy Before Convenience
9. Safe Metadata Only
10. Capability Discovery Before Consumption

## 10. Non-Goals

Voice Identity does not:

- manage permissions
- manage coordinator logic
- manage room context
- manage activity context
- manage devices
- manage intent routing
- manage automation execution

Concierge does not:

- store vectors
- generate embeddings
- perform attribution
- own Voiceprint storage

## 11. Consequences

Positive consequences:

- clean bounded domains
- independent deployment
- future attribution support
- strong privacy boundary
- optional platform capability model
- HACS-friendly architecture

Tradeoffs:

- additional service complexity
- sidecar lifecycle management
- version negotiation requirements
- capability discovery requirements

## 12. Implementation Guidance

Future implementation work must comply with this ADR.

If an implementation requires any of the following, then architecture is being violated:

- Concierge storing vectors
- Concierge generating embeddings
- Concierge performing attribution
- bypassing Voice Identity ownership

## 13. Consistency Review (VI-02 through VI-06)

This ADR is consistent with the approved direction from:

- VI-02 Technology Selection
- VI-03 Voiceprint Generation Contract
- VI-04 Voiceprint Artifact Contract
- VI-05 Voice Identity Service API
- VI-06 Concierge Integration Contract

No architecture redesign is introduced by this ADR.

This ADR ratifies and locks previously accepted decisions as implementation baseline.

## 14. Final ADR Statement

Architecture Decision:

Voice Identity is a first-class HTBW platform service responsible for identity generation, identity lifecycle, and future speaker attribution.

Voice Identity owns Voiceprints.

Concierge consumes Identity Context.

This architecture is accepted and becomes the foundation for future implementation work.

Status:

ACCEPTED

Supersedes:

None

Superseded By:

Not Applicable
