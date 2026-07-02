# Voice Identity Trust And Data Residency Policy

## Purpose

This policy defines the default trust model for Concierge voice identity and person-aware interaction.

It establishes how voice samples, voice profiles, and person identity data are handled when the system is designed to remain local-first.

This policy is part of the Concierge architecture and must align with Homes That Behave Well principles.

---

## Core Principle

Local-first is the default.

If the home can perform voice identity, matching, enrollment, and personalization inside the home network, that is the preferred architecture.

Voice identity must feel trustworthy, explainable, and bounded.

---

## Local-First Voice Policy

Voice identity capabilities should remain inside the home network whenever practical.

This includes:

- voice sample capture
- speaker embedding generation
- enrollment and profile updates
- speaker attribution
- confidence scoring
- local storage of voice profiles
- profile deletion and reset

Voice samples and voice profiles should not leave the home network by default.

---

## Cloud Assistance Exception Policy

Cloud services may only be used when:

- the user has explicitly opted in
- the purpose is clearly explained
- the system cannot satisfy the function locally
- the cloud usage is bounded to the specific approved task

If a cloud service is used, Concierge must explain:

- what is being sent
- why it is being sent
- whether it is temporary or stored
- how the user can revoke consent

Cloud assistance must never become the hidden default path for identity.

---

## Data Residency Policy

Person identity data should remain local by default.

Data in scope:

- voice samples
- speaker embeddings
- enrolled profiles
- confidence history
- consent state
- learning records

Rules:

- data must be stored on local infrastructure when possible
- data movement outside the home network must be explicit
- raw audio must be minimized or discarded after processing when possible
- retention must be bounded and explainable

---

## Consent And Transparency Policy

Trust requires clear consent.

Requirements:

- enrollment must be explicit
- device binding must be explicit
- voice training must be explicit
- deletion and disable paths must be explicit
- the user must be told when the system is local-only or cloud-assisted

The system must never silently upload voice identity data.

---

## Operational Policy

When local processing is available:

- use it first
- keep decisions deterministic
- keep identity matching explainable
- preserve room-first and person-aware fusion rules

When local confidence is low:

- fall back to neutral behavior
- do not guess with false certainty
- continue deterministic command processing

---

## Exception Governance

Any exception to local-first handling must be:

- documented
- consented to
- scoped to a bounded use case
- reversible
- visible in UI and diagnostics

Exceptions must be reviewed as architecture changes, not as hidden implementation details.

---

## Final Principle

If the home can know who is speaking and respond well without sending voice identity outside the network, that is the preferred path.

Cloud use is an exception, not the foundation.

See also: [identity-governance-reference.md](identity-governance-reference.md)
