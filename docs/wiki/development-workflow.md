# Development Workflow

## Architecture-First

Architecture, contracts, and ADR boundaries are authoritative. Implementations must preserve service boundaries and privacy constraints.

## Issue-Driven Development

Work is scoped and validated by issue acceptance criteria and dependency gates.

## Dependency Gates

Production-hardening dependencies (VI-121 through VI-129) must remain green before closing release-critical issues.

## Acceptance Review

Each implementation closes with explicit validation evidence, counts, and readiness verdicts.

## Remediation Workflow

If gates fail:

1. classify failure
2. apply minimal targeted fix
3. preserve contracts and privacy boundaries
4. re-run affected suites
5. document remediation

## Closure Workflow

1. run required suites
2. confirm docs and checklists updated
3. confirm CI workflow coverage
4. produce readiness verdict
