# ADR: Voice Identity as Standalone Repository

## 1. Status

Accepted (initial foundation).

## 2. Context

Concierge enrollment workflows are operational, but Build Voice Profile currently writes placeholder metadata rather than a durable biometric speaker fingerprint.

Voice identity capability introduces ML/runtime concerns, model lifecycle concerns, and biometric artifact handling that should be isolated from Concierge orchestration concerns.

## 3. Decision

Voice Identity will be implemented as a standalone HTBW repository and service consumed by Concierge.

## 4. Repository Boundary

Voice Identity owns speaker fingerprint generation, fingerprint artifact lifecycle, attribution model/versioning, and runtime speaker attribution result contracts.

## 5. Concierge Boundary

Concierge owns room context, people configuration, permission policy, coordinator behavior, enrollment orchestration, and user experience.

## 6. Voice Identity Responsibilities

- Build durable speaker fingerprints from enrollment audio references.
- Manage fingerprint artifact references and schema/model metadata.
- Produce runtime speaker attribution decisions and confidence outputs.
- Return safe reason codes for no-match and low-confidence outcomes.
- Own short-lived runtime attribution context records and expiry lifecycle.

## 7. Non-Responsibilities

Voice Identity does not own:

- room context
- permission evaluation policy decisions
- coordinator orchestration
- enrollment UI
- capture provider orchestration
- Home Assistant person profile ownership

## 8. Local-First Requirement

Voice Identity must support local-first operation.

Cloud dependency is not required for baseline operation.

## 9. HACS / Distribution Considerations

Concierge remains HACS-friendly by consuming Voice Identity as an optional local capability.

Voice Identity can evolve dependency/model stacks independently.

## 10. Privacy and Security

- raw recordings are temporary enrollment artifacts
- fingerprint artifacts are durable, protected, and local-first
- vectors/embeddings are not exposed in diagnostics, repairs, telemetry, service responses, or session projection payloads

## 11. Future Coordinator Integration

Concierge coordinator consumes only safe identity resolution outputs from Voice Identity:

- matched person identifier
- voice profile identifier
- confidence
- reason code

Coordinator/Concierge correlation keys such as `conversation_id`, `device_id`,
and `satellite_id` are lookup keys only and are not identity authority.

Runtime attribution context reuse must remain short-lived by default:

- high confidence known: 30 seconds
- medium confidence known: 15 seconds
- low confidence or ambiguous: 5 to 10 seconds
- unknown/unavailable: no reuse

Absolute cap: 60 seconds unless superseded by accepted ADR authority.

## 12. Consequences

Positive:

- isolates ML/runtime dependencies from Concierge
- preserves Concierge role as context and orchestration engine
- supports optional capability enablement
- protects biometric lifecycle behind dedicated component boundaries

Tradeoffs:

- introduces cross-repository/service integration complexity
- requires clear contracts, health checks, and version governance
