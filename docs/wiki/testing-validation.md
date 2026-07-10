# Testing and Validation

## Test Categories

- diagnostics
- repairs
- health
- attribution
- identity context
- compatibility
- performance
- fault injection
- release readiness
- HACS
- hassfest

## Core Validation Suites

- tests/test_diagnostics_provider.py
- tests/test_repairs.py
- tests/test_health_telemetry.py
- tests/test_attribution_foundation.py
- tests/test_identity_context.py
- tests/test_compatibility_migration_matrix.py
- tests/test_performance_resource_hardening.py
- tests/test_fault_injection_and_recovery.py
- tests/test_release_readiness.py
- tests/test_hacs_release_readiness.py

## CI Validation

GitHub Actions workflows provide release packaging validation:

- HACS Validation
- Validate with hassfest

Local validation does not replace required CI outcomes.
