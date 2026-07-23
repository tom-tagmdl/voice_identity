# Voice Identity Setup

This page is the dedicated help target for the Home Assistant setup screen `?` icon.

## What The Setup Screen Does

The Voice Identity setup screen writes the runtime defaults for the integration entry. Those values are stored in the config entry and can be adjusted later from the options flow.

## Fields

- Service settings control startup behavior and cache size.
- Storage settings control where Voice Identity persists artifacts.
- Generation settings control model preference and sample thresholds.
- Cleanup settings control background lifecycle housekeeping.
- Diagnostics settings control the safe diagnostics projection.
- Feature flag settings control optional runtime behavior.
- Attribution settings control confidence and context behavior.

## Recommended Values

Use the defaults unless you have a specific deployment reason to change them.

- Keep storage encryption required enabled.
- Keep diagnostics allowlist-only enabled.
- Keep runtime attribution disabled unless you are validating attribution workflows.
- Keep repairs enabled so readiness guidance remains available.

## Concierge Alignment Requirements

When Voice Identity is used with Concierge enrollment:

1. Ensure both integrations are updated to validated compatible builds.
2. Ensure model_preference is present in supported_models.
3. Confirm service runtime is enabled.
4. Confirm generation health before running profile build from Concierge.

## Development Testing Mode

Development builds can use deterministic model execution for end-to-end workflow validation.

1. Open Voice Identity options.
2. Enable feature flag: enable experimental models.
3. Save and reload Voice Identity.
4. Retry Concierge build profile.

This mode validates enrollment/generation orchestration flow and persistence contracts, but does not provide production biometric model fidelity.

## After Saving

1. Save the form.
2. Confirm Home Assistant reloads the integration entry.
3. Validate the services and readiness surfaces from the Voice Identity wiki.
4. Use the integration's reconfigure or options flow later if you need to change the runtime defaults.

## Related Pages

- [Wiki Index](index.md)
- [Runtime Requirements](runtime-requirements.md)
- [Troubleshooting](troubleshooting.md)
- [Services](services.md)
- [Operational Runbook](operational-runbook.md)
