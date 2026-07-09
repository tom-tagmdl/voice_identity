# Voice Identity Architecture

## Conceptual Enrollment Flow

Enrollment Audio
->
Voice Identity
->
Speaker Fingerprint
->
Fingerprint Artifact Reference
->
Concierge VoiceProfile Metadata

## Future Runtime Flow

Incoming Audio
->
Voice Identity
->
Speaker Attribution Result
->
Concierge Coordinator
->
Person Context
->
Permission Evaluation
->
Action

## Ownership

Voice Identity owns:

- fingerprint generation
- fingerprint model and version identity
- fingerprint quality scoring
- fingerprint artifact reference lifecycle
- runtime speaker attribution
- speaker match confidence
- no-match and low-confidence reason codes

Concierge owns:

- people
- permissions
- rooms
- coordinator
- enrollment orchestration
- user interface
- capture providers
- storage policy integration

## Boundary Principle

Concierge consumes Voice Identity through explicit contracts and should not embed fingerprint engine internals.
