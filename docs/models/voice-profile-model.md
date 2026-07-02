# Voice Profile Model

## Purpose

The Voice Profile Model defines how Concierge stores and resolves speaker identity for enrolled household members.

This model is for speaker attribution and interaction style only.

---

## Core Principle

A voice profile describes how a person sounds to the system.

It does not authenticate access.

It contributes to likely speaker attribution.

---

## Voice Profile Structure

Example structure:

voice_profile:
  person_id: person.tom
  enabled: true
  enrollment_state: active
  sample_count: 12
  confidence: 0.87
  last_enrolled_at: 2026-07-01T10:00:00Z
  last_verified_at: 2026-07-01T10:10:00Z
  training_mode: opt_in
  metadata:
    created_at: 2026-07-01T09:50:00Z
    updated_at: 2026-07-01T10:10:00Z

---

## Required Fields

- person_id
- enabled
- enrollment_state
- sample_count
- confidence
- metadata.created_at
- metadata.updated_at

---

## Enrollment State

Allowed values:

- pending
- active
- paused
- revoked
- deleted

---

## Attribution Snapshot

Example runtime snapshot:

voice_attribution_snapshot:
  person_id: person.tom
  confidence: 0.91
  top_candidates:
    - person.tom
    - person.david
  attribution_factors:
    - speaker_embedding_match
    - presence_match
    - room_proximity_match
  expires_at: 2026-07-01T10:15:00Z

---

## Consent Model

Enrollment and voice training require explicit consent.

Example:

consent:
  voice_training_enabled: true
  granted_at: 2026-07-01T09:55:00Z
  revoked_at: null

Rules:

- revocation disables use immediately
- deletion removes enrolled voice profiles from active use

---

## Learning Record Model

Example:

voice_adjustment:
  person_id: person.tom
  trigger: explicit_correction
  confidence_change: +0.05
  created_at: 2026-07-01T10:20:00Z
  reversible: true

---

## Validation Rules

- disabled profiles must not be applied
- deleted profiles must not remain active
- stale attribution snapshots must not persist beyond freshness policy
- all updates must be auditable

---

## Final Principle

The voice profile model should help Concierge recognize the speaker while remaining bounded, revocable, and explainable.
