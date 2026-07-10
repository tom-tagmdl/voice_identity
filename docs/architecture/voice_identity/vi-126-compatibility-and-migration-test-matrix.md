# VI-126 Compatibility and Migration Test Matrix

## Status

Implemented.

## Dependency Gate Verification

VI-126 dependency gate is satisfied by repository-implemented public surfaces:

From VI-124:
- canonical Identity Context contract and projection
- canonical states: known, unknown, low_confidence, unavailable
- read-only service surface: voice_identity.get_identity_context
- privacy-safe no-internal-leak projection behavior

From VI-125:
- read-only service surfaces: voice_identity.get_health and voice_identity.get_telemetry
- readiness outputs: attribution_readiness and compatibility_readiness
- privacy-safe health/telemetry projection behavior

VI-126 consumes these public surfaces only.

## Purpose

VI-126 defines and executes deterministic compatibility and migration validation across contract, schema, provider, and model versions.

VI-126 validates migration-required behavior and supported/unsupported upgrade and downgrade paths.

VI-126 does not redesign runtime architecture.

## Scope

Included:
- compatibility matrix definition and execution
- migration scenario matrix definition and execution
- contract/schema/provider/model compatibility validation
- upgrade and downgrade path validation
- migration-required detection and fail-closed behavior validation
- compatibility-readiness validation through VI-125 projections
- diagnostics and repairs integration validation through VI-121 and VI-122 surfaces
- privacy-boundary validation for compatibility and migration outputs

Excluded:
- new runtime attribution behavior
- new identity-context behavior
- new diagnostics framework
- new repair framework
- new health or telemetry architecture
- new migration engine
- performance/resource hardening (VI-127)
- fault-injection hardening (VI-128)
- release readiness/runbook work (VI-129)

## Matrix Definition

The executable matrix is defined in test code and includes explicit dimensions:
- source_version
- target_version
- artifact_schema_version
- contract_version
- provider_version
- model_version
- expected_status
- migration_required
- downgrade_supported
- expected_reason_code
- expected_health_status
- expected_compatibility_readiness
- expected_operator_guidance

The matrix is represented as 40 deterministic rows in:
- tests/test_compatibility_migration_matrix.py

## Version Fixtures

Repository implementations currently expose current versions as canonical values for most public contracts and schemas.

When historical compatibility versions are not implemented as production runtime behavior, VI-126 uses test-only fixtures to model:
- current supported version
- previous-version fixture
- unsupported future version
- unsupported legacy version
- missing version metadata
- malformed version metadata

These fixtures are test-only and do not claim production support for unsupported versions.

## Migration Behavior Validation

VI-126 validates migration-required behavior using existing repository surfaces:
- configuration schema migration-required detection
- health state propagation with migration_required
- compatibility readiness fail-closed projection when migration blocks compatibility

If migration execution is not present, VI-126 validates deterministic detection and safe fail-closed outputs.

## Upgrade and Downgrade Validation

Upgrade validation covers:
- current to current compatible path
- partially compatible path requiring upgrade action
- unsupported upgrade path

Downgrade validation covers:
- deterministic behavior when downgrade is not supported by current version contracts
- safe unsupported response with deterministic reason codes and guidance

## Health and Telemetry Relationship

VI-126 consumes VI-125 public readiness surfaces only.

Validation includes:
- compatibility_readiness ready/degraded/unavailable behavior
- privacy-safe telemetry compatibility projection

No parallel health model is introduced.

## Diagnostics and Repairs Relationship

VI-126 consumes VI-121 diagnostics and VI-122 repairs outputs.

Validation includes safe machine-readable fields:
- reason_code
- repair_hint_code
- suggested_next_action_code
- is_repairable_candidate where surfaced

No repair execution is introduced.

## Privacy Boundaries

Compatibility/migration outputs and test projections remain privacy-safe.

Never exposed:
- raw audio
- transcripts
- embeddings/vectors
- fingerprint payloads
- storage paths/filesystem internals
- provider/model internals beyond contract-safe metadata
- secrets/tokens/credentials
- raw exception traces

## Supported and Unsupported Paths

Supported (current implementation):
- current contract/schema compatibility
- deterministic partial compatibility and unsupported compatibility signaling
- deterministic migration-required detection
- deterministic fail-closed unavailable behavior for missing dependencies

Unsupported (current implementation):
- direct runtime downgrade support across multiple production contract versions
- production migration engine execution beyond current configuration/version validation surfaces

Unsupported paths are validated for deterministic safe rejection.

## Boundary Statement

VI-126 defines and executes compatibility and migration validation.

VI-126 does not implement performance hardening.

VI-126 does not implement resource hardening.

VI-126 does not implement fault injection.

VI-126 does not implement release readiness.

VI-126 does not expose Voice Identity internals.
