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

## Concierge Build Fails With generation_backend_unavailable

- Symptom: Concierge build profile fails with completion_not_ready and generation backend unavailable.
- Cause: Voice Identity model execution provider is not healthy.
- Remediation:
	1. Ensure Voice Identity runtime is enabled.
	2. In development environments, enable experimental models and reload.
	3. Re-run build profile after readiness refresh.

## Concierge Build Fails With model_provider_unavailable:model_failed

- Symptom: Concierge build profile fails after calling complete_voice_enrollment.
- Cause: Generation request reached Voice Identity, but model provider could not execute.
- Remediation:
	1. Validate Voice Identity health state.
	2. Verify model_preference is in supported_models.
	3. In development environments, enable experimental models and reload.

## HACS Validation Fails

- Inspect workflow run: HACS Validation.
- Correct repository metadata or structure issues.
- Re-run workflow until green.

## hassfest Validation Fails

- Inspect workflow run: Validate with hassfest.
- Correct manifest/services/translations/domain alignment issues.
- Re-run workflow until green.
