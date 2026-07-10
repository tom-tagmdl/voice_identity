# Troubleshooting

## Integration Does Not Load

- Verify manifest and integration domain are `voice_identity`.
- Check Home Assistant logs for startup failures.
- Confirm Home Assistant restart was performed after installation/update.

## Service Missing

- Verify integration loaded successfully.
- Verify expected services are registered.
- Re-run setup and confirm runtime entry exists.

## Diagnostics Unavailable

- Call `voice_identity.get_diagnostics` and inspect reason_code.
- If runtime unavailable, restore runtime load first.
- Re-check health readiness surfaces after remediation.

## Repair Unavailable

- Call `voice_identity.get_repairs`.
- If diagnostics unavailable, restore diagnostics/runtime first.

## Attribution Unavailable

- Call `voice_identity.attribute_speaker` and inspect reason_code.
- Validate health and readiness (`attribution_readiness`).
- Resolve model/registry/dependency availability issues.

## Identity Context Unavailable

- Call `voice_identity.get_identity_context`.
- Validate attribution availability and health readiness first.

## Model Backend Unavailable

- Validate backend/provider availability in diagnostics and health outputs.
- Follow repair guidance and re-check telemetry/health.

## HACS Validation Fails

- Inspect workflow run: HACS Validation.
- Correct repository metadata or structure issues.
- Re-run workflow until green.

## hassfest Validation Fails

- Inspect workflow run: Validate with hassfest.
- Correct manifest/services/translations/domain alignment issues.
- Re-run workflow until green.
