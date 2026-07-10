<img alt="voice_identity" src="https://github.com/user-attachments/assets/d8cc1489-5c5e-461c-810e-fc34b6f0077c" />


# Voice Identity

Voice Identity is a standalone Home Assistant custom integration that provides local-first, privacy-safe voice identity service surfaces for diagnostics, repairs, health, telemetry, advisory attribution, and identity context projection.

## What Voice Identity Is

- A standalone Home Assistant custom integration.
- The HTBW service responsible for speaker fingerprint generation and lifecycle ownership.
- The system that provides advisory attribution evidence and identity context projection.

## What Problem It Solves

Voice Identity provides a dedicated identity service boundary so consumers can use safe identity outputs without embedding biometric internals or cross-domain implementation details.

## What It Does Today

- Exposes diagnostics (`voice_identity.get_diagnostics`).
- Exposes repair recommendations (`voice_identity.get_repairs`).
- Exposes health (`voice_identity.get_health`).
- Exposes telemetry (`voice_identity.get_telemetry`).
- Exposes advisory attribution (`voice_identity.attribute_speaker`).
- Exposes identity context projection (`voice_identity.get_identity_context`).
- Validates compatibility and migration behavior.
- Validates performance/resource and fault-recovery hardening baselines.
- Provides release-readiness and operational runbook validation.

## What It Does Not Do

- Does not redesign Concierge behavior.
- Does not own room context, permissions, or coordinator policy.
- Does not provide authentication or authorization decisions.
- Does not export external telemetry pipelines.

## Architectural Principles

- Voice Identity is a standalone platform service.
- Concierge consumes safe public outputs only.
- Capability discovery and readiness surfaces are first-class runtime contracts.
- Attribution is advisory evidence, not identity truth.
- Identity Context is behavioral context, not authentication or authorization.

## Privacy Guarantees

Voice Identity does not expose:

- raw audio
- vectors
- embeddings
- fingerprint vectors
- fingerprint payload internals
- artifacts or artifact internals
- storage paths
- secrets or tokens
- exception traces

## Local-First Design

Voice Identity is designed for local-first operation. Cloud dependency is not required for baseline integration operation.

## Installation Through HACS (Custom Repository)

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository:
	- `https://github.com/tom-tagmdl/voice_identity`
3. Select repository type: Integration.
4. Install Voice Identity.
5. Restart Home Assistant.
6. Add and configure the integration from Home Assistant Integrations.
7. Verify services and readiness surfaces:
	- `voice_identity.get_diagnostics`
	- `voice_identity.get_repairs`
	- `voice_identity.get_health`
	- `voice_identity.get_telemetry`
	- `voice_identity.attribute_speaker`
	- `voice_identity.get_identity_context`

This repository is documented for HACS custom repository installation. It does not claim default HACS store listing.

## Manual Installation (Fallback)

1. Copy `custom_components/voice_identity` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Verify the integration loads.
4. Verify the services listed above are available.

## Home Assistant Restart Requirement

After installation or update, restart Home Assistant before validating service availability.

## Available Services

- `voice_identity.get_diagnostics`: safe diagnostics projection.
- `voice_identity.get_repairs`: recommendation-only repair guidance.
- `voice_identity.get_health`: operational health projection.
- `voice_identity.get_telemetry`: privacy-safe telemetry projection.
- `voice_identity.attribute_speaker`: advisory attribution evidence.
- `voice_identity.get_identity_context`: canonical identity context projection.

## Diagnostics, Repairs, Health, Telemetry, Attribution, and Identity Context

- Diagnostics are deterministic and sanitized.
- Repairs are recommendation-only and do not execute actions.
- Health and telemetry expose readiness, including `attribution_readiness` and `compatibility_readiness`.
- Attribution remains advisory and fail-closed.
- Identity context maps to canonical states: `known`, `unknown`, `low_confidence`, `unavailable`.

## Operational Readiness Status

Production-hardening artifacts VI-121 through VI-129 are implemented and validated through repository test suites.

## Known Limitations

- Attribution outputs are advisory evidence.
- Identity context is not authn/authz.
- No external telemetry export is provided.
- Release tagging should occur only after GitHub Actions validation workflows are green.

## Non-Applicable Gold Rules

Voice Identity is service-only, so some Home Assistant Gold expectations are not
applicable and should not be treated as missing work:

- No device discovery flow is required.
- No firmware update support is required.
- No device or entity surface is required unless a future feature introduces
	one intentionally.
- No reauth flow is required unless the integration gains expiring credentials
	or another external dependency that needs it.

## Troubleshooting

- Integration does not load: verify manifest/domain alignment and restart Home Assistant.
- Service missing: verify integration loaded and runtime entry exists.
- Diagnostics unavailable: run `voice_identity.get_diagnostics` and inspect `reason_code`.
- Repairs unavailable: run `voice_identity.get_repairs` and recover diagnostics/runtime availability.
- Attribution unavailable: run `voice_identity.attribute_speaker` and inspect health/readiness.
- Identity context unavailable: verify attribution and health readiness first.
- Model backend unavailable: inspect diagnostics/health reason codes and follow repair guidance.
- HACS validation fails: check GitHub Actions `HACS Validation`.
- hassfest validation fails: check GitHub Actions `Validate with hassfest`.

## Developer Documentation

- Developer wiki index: `docs/wiki/index.md`
- Architecture docs: `docs/architecture/`
- Operational runbook: `docs/architecture/voice_identity/vi-129-release-readiness-and-operational-runbook.md`
- Release checklist: `docs/RELEASE_CHECKLIST.md`

## Release Status

- Release notes draft: `docs/releases/v0.1.0.md`
- CI release validation workflows:
  - `.github/workflows/hacs.yml`
  - `.github/workflows/hassfest.yml`

Repository should be tagged and released only after required tests and GitHub Actions workflows pass.
