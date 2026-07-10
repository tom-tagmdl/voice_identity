"""Voiceprint revision manager.

This layer owns deterministic revision numbering and lineage validation above
the registry, while deferring lifecycle transitions to the lifecycle manager.
"""

from __future__ import annotations

from dataclasses import dataclass

from .health_state import HealthState
from .voiceprint_lifecycle import VoiceprintLifecycleManager
from .voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRecord,
    VoiceprintRegistry,
    VoiceprintRegistryValidationError,
    VoiceprintSubjectId,
    create_voiceprint_record,
)


class VoiceprintRevisionError(Exception):
    """Base exception for revision manager failures."""


class VoiceprintRevisionNotLoadedError(VoiceprintRevisionError):
    """Raised when revision manager is used before readiness."""


class VoiceprintRevisionConflictError(VoiceprintRevisionError):
    """Raised when revision sequence or lineage conflicts are detected."""


class VoiceprintRevisionValidationError(VoiceprintRevisionError):
    """Raised when revision metadata is invalid."""


@dataclass(slots=True, frozen=True)
class VoiceprintRevisionHealth:
    """Revision manager health integration payload."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class VoiceprintRevisionManager:
    """Owns immutable revision-chain semantics for voiceprint records."""

    def __init__(
        self,
        *,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
    ) -> None:
        self._registry = registry
        self._lifecycle_manager = lifecycle_manager
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        registry: VoiceprintRegistry,
        lifecycle_manager: VoiceprintLifecycleManager,
    ) -> VoiceprintRevisionManager:
        return cls(registry=registry, lifecycle_manager=lifecycle_manager)

    def get_next_revision(self, lineage_root_id: VoiceprintId | None = None) -> int:
        """Return deterministic next revision number for a lineage."""
        self._ensure_loaded()
        if lineage_root_id is None:
            return 1

        records = self._registry.get_by_lineage_root_id(lineage_root_id)
        if not records:
            return 1

        self.validate_revision_sequence(lineage_root_id)
        return max(record.lineage.revision for record in records) + 1

    def get_latest_record(self, lineage_root_id: VoiceprintId) -> VoiceprintRecord:
        """Return the latest record in a lineage by deterministic revision order."""
        self._ensure_loaded()
        chain = self.traverse_lineage(lineage_root_id)
        if not chain:
            raise VoiceprintRevisionValidationError("voiceprint_revision_lineage_invalid")
        return chain[-1]

    def traverse_lineage(self, lineage_root_id: VoiceprintId) -> tuple[VoiceprintRecord, ...]:
        """Return validated revision chain from root to latest."""
        self._ensure_loaded()
        records = self._registry.get_by_lineage_root_id(lineage_root_id)
        if not records:
            return ()
        self._validate_records(records, lineage_root_id)
        return tuple(sorted(records, key=lambda item: item.lineage.revision))

    def validate_revision_sequence(self, lineage_root_id: VoiceprintId) -> None:
        """Validate revision numbering and lineage structure for one chain."""
        self._ensure_loaded()
        records = self._registry.get_by_lineage_root_id(lineage_root_id)
        self._validate_records(records, lineage_root_id)

    def prepare_initial_record(
        self,
        *,
        voiceprint_id: str,
        artifact_id: str,
        subject_id: str,
        model_name: str,
        model_version: str,
        schema_version: int,
        lifecycle_state: VoiceprintLifecycleState = VoiceprintLifecycleState.PENDING,
        active: bool = False,
    ) -> VoiceprintRecord:
        """Prepare the root revision record for a new lineage."""
        self._ensure_loaded()
        return create_voiceprint_record(
            voiceprint_id=voiceprint_id,
            artifact_id=artifact_id,
            subject_id=subject_id,
            revision=1,
            lifecycle_state=lifecycle_state,
            active=active,
            model_name=model_name,
            model_version=model_version,
            schema_version=schema_version,
            lineage_root_id=voiceprint_id,
        )

    def prepare_next_revision_record(
        self,
        *,
        current_voiceprint_id: VoiceprintId,
        new_voiceprint_id: str,
        new_artifact_id: str,
        model_name: str,
        model_version: str,
        schema_version: int,
        lifecycle_state: VoiceprintLifecycleState = VoiceprintLifecycleState.PENDING,
        active: bool = False,
    ) -> VoiceprintRecord:
        """Prepare the next immutable revision record in an existing lineage."""
        self._ensure_loaded()
        current = self._registry.get_by_voiceprint_id(current_voiceprint_id)
        lineage_root = current.lineage.lineage_root_id
        next_revision = self.get_next_revision(lineage_root)
        latest = self.get_latest_record(lineage_root)
        if latest.voiceprint_id != current.voiceprint_id:
            raise VoiceprintRevisionConflictError("voiceprint_revision_conflict")

        return create_voiceprint_record(
            voiceprint_id=new_voiceprint_id,
            artifact_id=new_artifact_id,
            subject_id=current.subject_id.value,
            revision=next_revision,
            lifecycle_state=lifecycle_state,
            active=active,
            model_name=model_name,
            model_version=model_version,
            schema_version=schema_version,
            lineage_root_id=lineage_root.value,
            parent_voiceprint_id=current.voiceprint_id.value,
            supersedes=current.voiceprint_id.value,
        )

    async def coordinate_supersession(
        self,
        *,
        current_voiceprint_id: VoiceprintId,
        replacement_voiceprint_id: VoiceprintId,
    ) -> tuple[VoiceprintRecord, VoiceprintRecord]:
        """Coordinate supersession lifecycle using validated revision semantics."""
        self._ensure_loaded()
        current = self._registry.get_by_voiceprint_id(current_voiceprint_id)
        replacement = self._registry.get_by_voiceprint_id(replacement_voiceprint_id)

        if replacement.lineage.parent_voiceprint_id != current.voiceprint_id:
            raise VoiceprintRevisionValidationError("voiceprint_revision_parent_missing")
        if replacement.lineage.supersedes != current.voiceprint_id:
            raise VoiceprintRevisionValidationError("voiceprint_revision_supersession_invalid")
        if replacement.lineage.lineage_root_id != current.lineage.lineage_root_id:
            raise VoiceprintRevisionValidationError("voiceprint_revision_lineage_invalid")
        if replacement.lineage.revision != current.lineage.revision + 1:
            raise VoiceprintRevisionValidationError("voiceprint_revision_gap")

        return await self._lifecycle_manager.supersede_record(
            current_voiceprint_id=current_voiceprint_id,
            replacement_voiceprint_id=replacement_voiceprint_id,
        )

    async def validate_health(self) -> VoiceprintRevisionHealth:
        """Validate revision-manager readiness from registry state."""
        if not self._loaded:
            return VoiceprintRevisionHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_revision_not_loaded",),
                details={"loaded": False},
            )

        try:
            for lineage_root in self._unique_lineage_roots():
                self.validate_revision_sequence(lineage_root)
        except VoiceprintRevisionConflictError as err:
            return VoiceprintRevisionHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(str(err),),
                details={"loaded": True},
            )
        except VoiceprintRevisionValidationError as err:
            return VoiceprintRevisionHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(str(err),),
                details={"loaded": True},
            )
        except VoiceprintRegistryValidationError:
            return VoiceprintRevisionHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_revision_not_loaded",),
                details={"loaded": False},
            )

        return VoiceprintRevisionHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True, "lineage_count": len(self._unique_lineage_roots())},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise VoiceprintRevisionNotLoadedError("voiceprint_revision_not_loaded")

    def _unique_lineage_roots(self) -> tuple[VoiceprintId, ...]:
        roots = {record.lineage.lineage_root_id.value for record in self._registry.list_records()}
        return tuple(VoiceprintId.parse(root) for root in sorted(roots))

    def _validate_records(
        self,
        records: tuple[VoiceprintRecord, ...],
        lineage_root_id: VoiceprintId,
    ) -> None:
        if not records:
            return

        by_voiceprint_id = {record.voiceprint_id.value: record for record in records}
        revisions_seen: set[int] = set()
        sorted_records = sorted(records, key=lambda item: item.lineage.revision)

        root = sorted_records[0]
        if root.lineage.revision != 1:
            raise VoiceprintRevisionConflictError("voiceprint_revision_gap")
        if root.voiceprint_id != lineage_root_id:
            raise VoiceprintRevisionConflictError("voiceprint_revision_lineage_invalid")
        if root.lineage.parent_voiceprint_id is not None:
            raise VoiceprintRevisionConflictError("voiceprint_revision_lineage_invalid")
        if root.lineage.supersedes is not None:
            raise VoiceprintRevisionConflictError("voiceprint_revision_lineage_invalid")

        for record in sorted_records:
            cursor = record
            seen_chain: set[str] = set()
            while cursor.lineage.parent_voiceprint_id is not None:
                if cursor.voiceprint_id.value in seen_chain:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_cycle_detected")
                seen_chain.add(cursor.voiceprint_id.value)
                parent = by_voiceprint_id.get(cursor.lineage.parent_voiceprint_id.value)
                if parent is None:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_parent_missing")
                cursor = parent

        previous = None
        visited: set[str] = set()
        for expected_revision, record in enumerate(sorted_records, start=1):
            if record.lineage.lineage_root_id != lineage_root_id:
                raise VoiceprintRevisionConflictError("voiceprint_revision_lineage_invalid")
            if record.lineage.revision in revisions_seen:
                raise VoiceprintRevisionConflictError("voiceprint_revision_duplicate")
            revisions_seen.add(record.lineage.revision)
            if record.lineage.revision != expected_revision:
                raise VoiceprintRevisionConflictError("voiceprint_revision_gap")

            if record.voiceprint_id.value in visited:
                raise VoiceprintRevisionConflictError("voiceprint_revision_cycle_detected")
            visited.add(record.voiceprint_id.value)

            if previous is not None:
                if record.lineage.parent_voiceprint_id is None:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_parent_missing")
                if record.lineage.parent_voiceprint_id.value not in by_voiceprint_id:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_parent_missing")
                if record.lineage.parent_voiceprint_id != previous.voiceprint_id:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_lineage_invalid")
                if record.lineage.supersedes != previous.voiceprint_id:
                    raise VoiceprintRevisionConflictError("voiceprint_revision_supersession_invalid")
            previous = record
