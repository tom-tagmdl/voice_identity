"""Artifact integrity validation for voiceprint artifacts and revision records.

This layer is read-only. It validates persisted artifacts, metadata integrity,
and cross-layer consistency without modifying storage, registry, revisions, or
lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .artifact_persistence import (
    ArtifactPersistencePayloadError,
    EncryptedRepresentationEnvelope,
    _deserialize_envelope,
)
from .health_state import HealthState
from .storage_provider import (
    VoiceIdentityStorageArtifactNotFoundError,
    VoiceIdentityStorageReadError,
    VoiceprintStorageProvider,
)
from .voiceprint_registry import VoiceprintId, VoiceprintRegistry, VoiceprintRegistryError
from .voiceprint_revision import VoiceprintRevisionConflictError, VoiceprintRevisionManager


class IntegritySeverity(StrEnum):
    """Severity model for integrity validation findings."""

    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    CORRUPTED = "corrupted"
    UNAVAILABLE = "unavailable"


class IntegrityFindingType(StrEnum):
    """Finding categories for integrity validation."""

    ARTIFACT = "artifact"
    METADATA = "metadata"
    REVISION = "revision"
    CROSS_LAYER = "cross_layer"


@dataclass(slots=True, frozen=True)
class IntegrityFinding:
    """One safe, machine-readable integrity finding."""

    status: str
    finding_type: IntegrityFindingType
    severity: IntegritySeverity
    reason_code: str
    validation_timestamp: str
    affected_artifact_id: str | None
    affected_revision_id: str | None
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class ArtifactIntegrityResult:
    """Structured validation result for one artifact or scope."""

    status: IntegritySeverity
    findings: tuple[IntegrityFinding, ...]


@dataclass(slots=True, frozen=True)
class ArtifactIntegrityHealth:
    """Integrity validator health integration payload."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class ArtifactIntegrityValidator:
    """Read-only validator for artifact, metadata, and revision integrity."""

    def __init__(
        self,
        *,
        storage_provider: VoiceprintStorageProvider,
        registry: VoiceprintRegistry,
        revision_manager: VoiceprintRevisionManager,
    ) -> None:
        self._storage_provider = storage_provider
        self._registry = registry
        self._revision_manager = revision_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        storage_provider: VoiceprintStorageProvider,
        registry: VoiceprintRegistry,
        revision_manager: VoiceprintRevisionManager,
    ) -> ArtifactIntegrityValidator:
        return cls(
            storage_provider=storage_provider,
            registry=registry,
            revision_manager=revision_manager,
        )

    async def validate_voiceprint(self, voiceprint_id: VoiceprintId) -> ArtifactIntegrityResult:
        """Validate one registry record plus its backing artifact."""
        self._ensure_loaded()
        findings: list[IntegrityFinding] = []

        try:
            record = self._registry.get_by_voiceprint_id(voiceprint_id)
        except VoiceprintRegistryError:
            findings.append(
                _finding(
                    severity=IntegritySeverity.UNAVAILABLE,
                    reason_code="metadata_missing",
                    finding_type=IntegrityFindingType.METADATA,
                    affected_revision_id=voiceprint_id.value,
                )
            )
            return _result_from_findings(findings)

        try:
            payload = await self._storage_provider.load_artifact(record.artifact_id)
        except VoiceIdentityStorageArtifactNotFoundError:
            findings.append(
                _finding(
                    severity=IntegritySeverity.UNAVAILABLE,
                    reason_code="artifact_missing",
                    finding_type=IntegrityFindingType.ARTIFACT,
                    affected_artifact_id=record.artifact_id.value,
                    affected_revision_id=record.voiceprint_id.value,
                )
            )
            return _result_from_findings(findings)
        except VoiceIdentityStorageReadError:
            findings.append(
                _finding(
                    severity=IntegritySeverity.CORRUPTED,
                    reason_code="artifact_unreadable",
                    finding_type=IntegrityFindingType.ARTIFACT,
                    affected_artifact_id=record.artifact_id.value,
                    affected_revision_id=record.voiceprint_id.value,
                )
            )
            return _result_from_findings(findings)

        try:
            envelope = _deserialize_envelope(payload)
        except ArtifactPersistencePayloadError as err:
            findings.append(
                _finding(
                    severity=IntegritySeverity.CORRUPTED,
                    reason_code=_map_payload_error(str(err)),
                    finding_type=IntegrityFindingType.ARTIFACT,
                    affected_artifact_id=record.artifact_id.value,
                    affected_revision_id=record.voiceprint_id.value,
                )
            )
            return _result_from_findings(findings)

        findings.extend(_validate_record_against_envelope(record, envelope))
        findings.extend(await self._validate_revision_scope(record.lineage.lineage_root_id))
        if not findings:
            findings.append(
                _finding(
                    severity=IntegritySeverity.HEALTHY,
                    reason_code="artifact_integrity_ready",
                    finding_type=IntegrityFindingType.ARTIFACT,
                    affected_artifact_id=record.artifact_id.value,
                    affected_revision_id=record.voiceprint_id.value,
                    details={"payload_size": envelope.integrity.payload_size},
                )
            )
        return _result_from_findings(findings)

    async def validate_all(self) -> ArtifactIntegrityResult:
        """Validate all registry records and storage cross-layer consistency."""
        self._ensure_loaded()
        findings: list[IntegrityFinding] = []
        registry_records = self._registry.list_records()

        for record in registry_records:
            result = await self.validate_voiceprint(record.voiceprint_id)
            findings.extend(result.findings)

        storage_artifacts = await self._storage_provider.list_artifacts()
        registry_artifact_ids = {record.artifact_id.value for record in registry_records}
        for stored in storage_artifacts:
            if stored.artifact_id.value not in registry_artifact_ids:
                findings.append(
                    _finding(
                        severity=IntegritySeverity.WARNING,
                        reason_code="orphaned_artifact",
                        finding_type=IntegrityFindingType.CROSS_LAYER,
                        affected_artifact_id=stored.artifact_id.value,
                        details={"size_bytes": stored.size_bytes},
                    )
                )

        if not findings:
            findings.append(
                _finding(
                    severity=IntegritySeverity.HEALTHY,
                    reason_code="artifact_integrity_ready",
                    finding_type=IntegrityFindingType.CROSS_LAYER,
                )
            )
        return _result_from_findings(findings)

    async def validate_health(self) -> ArtifactIntegrityHealth:
        """Project validator findings into the shared health model."""
        if not self._loaded:
            return ArtifactIntegrityHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("artifact_integrity_validator_unavailable",),
                details={"loaded": False},
            )

        result = await self.validate_all()
        if result.status is IntegritySeverity.HEALTHY:
            return ArtifactIntegrityHealth(
                state=HealthState.HEALTHY,
                reason_codes=("artifact_integrity_ready",),
                details={"loaded": True, "finding_count": len(result.findings)},
            )

        if result.status in {IntegritySeverity.WARNING, IntegritySeverity.DEGRADED}:
            return ArtifactIntegrityHealth(
                state=HealthState.DEGRADED,
                reason_codes=tuple(sorted({finding.reason_code for finding in result.findings})),
                details={"loaded": True, "finding_count": len(result.findings)},
            )

        return ArtifactIntegrityHealth(
            state=HealthState.UNAVAILABLE,
            reason_codes=tuple(sorted({finding.reason_code for finding in result.findings})),
            details={"loaded": True, "finding_count": len(result.findings)},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("artifact_integrity_validator_unavailable")

    async def _validate_revision_scope(self, lineage_root_id: VoiceprintId) -> list[IntegrityFinding]:
        findings: list[IntegrityFinding] = []
        try:
            self._revision_manager.validate_revision_sequence(lineage_root_id)
        except VoiceprintRevisionConflictError as err:
            reason_code = str(err)
            if reason_code not in {
                "voiceprint_revision_duplicate",
                "voiceprint_revision_gap",
                "voiceprint_revision_lineage_invalid",
                "voiceprint_revision_parent_missing",
                "voiceprint_revision_supersession_invalid",
                "voiceprint_revision_cycle_detected",
            }:
                reason_code = "revision_inconsistent"
            findings.append(
                _finding(
                    severity=IntegritySeverity.DEGRADED,
                    reason_code=reason_code,
                    finding_type=IntegrityFindingType.REVISION,
                    affected_revision_id=lineage_root_id.value,
                )
            )
        except Exception:
            findings.append(
                _finding(
                    severity=IntegritySeverity.DEGRADED,
                    reason_code="revision_inconsistent",
                    finding_type=IntegrityFindingType.REVISION,
                    affected_revision_id=lineage_root_id.value,
                )
            )
        return findings


def _validate_record_against_envelope(
    record,
    envelope: EncryptedRepresentationEnvelope,
) -> list[IntegrityFinding]:
    findings: list[IntegrityFinding] = []
    if envelope.integrity.payload_size != len(envelope.encrypted_payload):
        findings.append(
            _finding(
                severity=IntegritySeverity.CORRUPTED,
                reason_code="payload_corrupted",
                finding_type=IntegrityFindingType.ARTIFACT,
                affected_artifact_id=record.artifact_id.value,
                affected_revision_id=record.voiceprint_id.value,
            )
        )
    if envelope.model_name != record.model_name or envelope.model_version != record.model_version:
        findings.append(
            _finding(
                severity=IntegritySeverity.DEGRADED,
                reason_code="metadata_invalid",
                finding_type=IntegrityFindingType.METADATA,
                affected_artifact_id=record.artifact_id.value,
                affected_revision_id=record.voiceprint_id.value,
            )
        )
    if envelope.schema_version != record.schema_version:
        findings.append(
            _finding(
                severity=IntegritySeverity.DEGRADED,
                reason_code="registry_inconsistent",
                finding_type=IntegrityFindingType.CROSS_LAYER,
                affected_artifact_id=record.artifact_id.value,
                affected_revision_id=record.voiceprint_id.value,
            )
        )
    return findings


def _result_from_findings(findings: list[IntegrityFinding]) -> ArtifactIntegrityResult:
    if not findings:
        return ArtifactIntegrityResult(status=IntegritySeverity.HEALTHY, findings=())

    severity_order = [
        IntegritySeverity.UNAVAILABLE,
        IntegritySeverity.CORRUPTED,
        IntegritySeverity.DEGRADED,
        IntegritySeverity.WARNING,
        IntegritySeverity.HEALTHY,
    ]
    for severity in severity_order:
        if any(finding.severity is severity for finding in findings):
            return ArtifactIntegrityResult(status=severity, findings=tuple(findings))
    return ArtifactIntegrityResult(status=IntegritySeverity.HEALTHY, findings=tuple(findings))


def _finding(
    *,
    severity: IntegritySeverity,
    reason_code: str,
    finding_type: IntegrityFindingType,
    affected_artifact_id: str | None = None,
    affected_revision_id: str | None = None,
    details: dict[str, bool | int | float | str | None] | None = None,
) -> IntegrityFinding:
    from .artifact_persistence import _utcnow_iso

    return IntegrityFinding(
        status=severity.value,
        finding_type=finding_type,
        severity=severity,
        reason_code=reason_code,
        validation_timestamp=_utcnow_iso(),
        affected_artifact_id=affected_artifact_id,
        affected_revision_id=affected_revision_id,
        details=details or {},
    )


def _map_payload_error(reason_code: str) -> str:
    if reason_code == "artifact_persistence_integrity_metadata_failed":
        return "digest_mismatch"
    if reason_code == "artifact_persistence_payload_not_encrypted":
        return "metadata_invalid"
    if reason_code == "artifact_persistence_payload_invalid":
        return "payload_corrupted"
    return "artifact_unreadable"
