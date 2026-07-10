# Voice Identity Release Checklist

## Pre-release

- [ ] Dependency test bundle green:
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
- [ ] HACS validation green (GitHub Actions: HACS Validation)
- [ ] hassfest validation green (GitHub Actions: Validate with hassfest)
- [ ] README updated for release
- [ ] Developer docs wiki updated
- [ ] Operational runbook updated (VI-129)
- [ ] manifest version reviewed
- [ ] hacs.json reviewed
- [ ] Release notes drafted
- [ ] Tag prepared

## Release

- [ ] Create GitHub tag
- [ ] Create GitHub release
- [ ] Include release notes
- [ ] Confirm HACS can install release from custom repository

## Post-release

- [ ] Install from HACS custom repository
- [ ] Restart Home Assistant
- [ ] Verify services are registered
- [ ] Verify diagnostics (voice_identity.get_diagnostics)
- [ ] Verify health (voice_identity.get_health)
- [ ] Verify repairs (voice_identity.get_repairs)
- [ ] Verify identity context (voice_identity.get_identity_context)
- [ ] Verify logs are clean
