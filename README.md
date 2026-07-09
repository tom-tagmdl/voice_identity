<img width="1536" height="1024" alt="voice_identity" src="https://github.com/user-attachments/assets/d1dcc208-242b-4667-a603-90a694395d8d" />
# Voice Identity

Voice Identity is the HTBW local-first speaker identity service.

It provides:

- speaker fingerprint generation from enrollment audio
- durable fingerprint artifact references
- future runtime speaker attribution
- confidence scoring
- safe identity-resolution contracts for Concierge

It does not own:

- room context
- permissions
- coordinator behavior
- enrollment UI
- Home Assistant person configuration
- Concierge workflow orchestration

Relationship:

Concierge
->
Voice Identity
->
resolved person / confidence / reason code

Voice Identity is intended to be consumed by Concierge, not embedded inside Concierge.

## Repository Scope

This repository currently contains architecture documentation, contracts, and scaffold interfaces.

No production fingerprint engine or model runtime is implemented yet.
