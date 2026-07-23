# Contracts

## Public Contract Overview

Voice Identity exposes privacy-safe service contracts for diagnostics, repairs, health, telemetry, advisory attribution, and identity context.

## Fingerprint Generation Result

Core fields include success, fingerprint reference metadata, model/schema metadata, quality score, and safe failure codes/messages.

## Attribution Result

Attribution is advisory evidence and includes status, confidence, confidence band, reason code, and safe hints.

## Runtime Attribution Record

Runtime attribution records are short-lived bridge records used for audio-time to
text-time handoff.

Required safe sections include:

- binding correlation (`conversation_id`, `device_id`, `satellite_id`, optional `room_id`)
- decision state and reason code
- confidence band
- freshness/validity metadata
- integrity presence flags

Voice Identity owns attribution context storage and expiry.

## Identity Context

Identity Context is a canonical projection with state (`known`, `not_required`,
`unknown`, `low_confidence`, `unavailable`) and safe metadata only.

`conversation_id` is used for correlation and is not a speaker-identity authority.

## Diagnostics

Diagnostics are sectioned, deterministic, and sanitized with allowlist-safe projections.

## Repairs

Repairs are recommendation-only outputs derived from diagnostics and reason-code mappings.

## Health and Telemetry

Health and telemetry expose deterministic operational projections and readiness surfaces.

## Privacy-Safe Projection Rules

Never expose:

- raw audio
- transcripts
- vectors or embeddings
- fingerprint payload internals
- storage paths
- secrets/tokens
- exception traces
