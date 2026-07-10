# Repairs

## Service

Use `voice_identity.get_repairs` for deterministic repair recommendations.

## Recommendation-Only Model

Repairs are guidance outputs only. The subsystem does not execute remediation actions.

## No Execution Boundary

Repair logic maps diagnostics reason codes to deterministic recommendation payloads and safe next actions.

## Operator Guidance

1. Collect diagnostics.
2. Collect repairs.
3. Execute remediation outside the repair service.
4. Re-run diagnostics and health checks to verify recovery.
