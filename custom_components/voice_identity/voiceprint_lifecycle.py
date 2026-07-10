"""Voiceprint lifecycle manager.

This layer owns lifecycle transition rules above the voiceprint registry while
preserving immutable artifact identity and registry/storage separation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .health_state import HealthState
from .voiceprint_registry import (
    VoiceprintId,
    VoiceprintLifecycleState,
    VoiceprintRecord,
    VoiceprintRegistry,
    VoiceprintRegistryRecordNotFoundError,
    VoiceprintRegistryValidationError,
    replace_voiceprint_record,
)


class VoiceprintLifecycleError(Exception):
    """Base exception for lifecycle manager failures."""


class VoiceprintLifecycleNotLoadedError(VoiceprintLifecycleError):
    """Raised when lifecycle manager is used before readiness."""


class VoiceprintLifecycleInvalidTransitionError(VoiceprintLifecycleError):
    """Raised when a lifecycle transition is invalid."""


class VoiceprintLifecycleConflictError(VoiceprintLifecycleError):
    """Raised when lifecycle constraints would be violated."""


class VoiceprintLifecycleSupersessionError(VoiceprintLifecycleError):
    """Raised when supersession metadata is invalid."""


@dataclass(slots=True, frozen=True)
class VoiceprintLifecycleHealth:
    """Lifecycle health integration payload."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class VoiceprintLifecycleManager:
    """Owns lifecycle state transitions above the voiceprint registry."""

    def __init__(self, *, registry: VoiceprintRegistry) -> None:
        self._registry = registry
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(cls, *, registry: VoiceprintRegistry) -> VoiceprintLifecycleManager:
        return cls(registry=registry)

    async def activate_record(self, voiceprint_id: VoiceprintId) -> VoiceprintRecord:
        """Activate a record if its lifecycle transition is valid and unique."""
        self._ensure_loaded()
        record = self._registry.get_by_voiceprint_id(voiceprint_id)
        self._assert_transition_allowed(record.lifecycle_state, VoiceprintLifecycleState.ACTIVE)
        self._ensure_no_other_active_conflict(record)

        updated = replace_voiceprint_record(
            record,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )
        return await self._registry.update_record(updated)

    async def mark_failed(self, voiceprint_id: VoiceprintId) -> VoiceprintRecord:
        """Transition a pending record to failed."""
        self._ensure_loaded()
        record = self._registry.get_by_voiceprint_id(voiceprint_id)
        self._assert_transition_allowed(record.lifecycle_state, VoiceprintLifecycleState.FAILED)
        updated = replace_voiceprint_record(
            record,
            lifecycle_state=VoiceprintLifecycleState.FAILED,
            active=False,
        )
        return await self._registry.update_record(updated)

    async def deactivate_record(self, voiceprint_id: VoiceprintId) -> VoiceprintRecord:
        """Transition an active record to inactive."""
        self._ensure_loaded()
        record = self._registry.get_by_voiceprint_id(voiceprint_id)
        self._assert_transition_allowed(record.lifecycle_state, VoiceprintLifecycleState.INACTIVE)
        updated = replace_voiceprint_record(
            record,
            lifecycle_state=VoiceprintLifecycleState.INACTIVE,
            active=False,
        )
        return await self._registry.update_record(updated)

    async def delete_record(self, voiceprint_id: VoiceprintId) -> VoiceprintRecord:
        """Apply lifecycle-level deletion semantics without deleting artifact bytes."""
        self._ensure_loaded()
        record = self._registry.get_by_voiceprint_id(voiceprint_id)
        self._assert_transition_allowed(record.lifecycle_state, VoiceprintLifecycleState.DELETED)
        updated = replace_voiceprint_record(
            record,
            lifecycle_state=VoiceprintLifecycleState.DELETED,
            active=False,
        )
        return await self._registry.update_record(updated)

    async def supersede_record(
        self,
        *,
        current_voiceprint_id: VoiceprintId,
        replacement_voiceprint_id: VoiceprintId,
    ) -> tuple[VoiceprintRecord, VoiceprintRecord]:
        """Supersede one record with another through metadata transitions only."""
        self._ensure_loaded()
        current = self._registry.get_by_voiceprint_id(current_voiceprint_id)
        replacement = self._registry.get_by_voiceprint_id(replacement_voiceprint_id)

        if current.voiceprint_id == replacement.voiceprint_id:
            raise VoiceprintLifecycleSupersessionError("voiceprint_supersession_invalid")

        if current.subject_id != replacement.subject_id:
            raise VoiceprintLifecycleSupersessionError("voiceprint_supersession_invalid")

        if current.lineage.lineage_root_id != replacement.lineage.lineage_root_id:
            raise VoiceprintLifecycleSupersessionError("voiceprint_supersession_invalid")

        if replacement.lineage.parent_voiceprint_id != current.voiceprint_id:
            raise VoiceprintLifecycleSupersessionError("voiceprint_supersession_invalid")

        if replacement.lineage.supersedes != current.voiceprint_id:
            raise VoiceprintLifecycleSupersessionError("voiceprint_supersession_invalid")

        self._assert_transition_allowed(current.lifecycle_state, VoiceprintLifecycleState.SUPERSEDED)
        self._assert_transition_allowed(replacement.lifecycle_state, VoiceprintLifecycleState.ACTIVE)
        self._ensure_no_other_active_conflict(replacement, excluded_ids={current.voiceprint_id.value})

        updated_current = replace_voiceprint_record(
            current,
            lifecycle_state=VoiceprintLifecycleState.SUPERSEDED,
            active=False,
            superseded_by=replacement.voiceprint_id,
        )
        updated_replacement = replace_voiceprint_record(
            replacement,
            lifecycle_state=VoiceprintLifecycleState.ACTIVE,
            active=True,
        )

        saved_current = await self._registry.update_record(updated_current)
        saved_replacement = await self._registry.update_record(updated_replacement)
        return saved_current, saved_replacement

    async def validate_health(self) -> VoiceprintLifecycleHealth:
        """Validate lifecycle readiness from current registry state."""
        if not self._loaded:
            return VoiceprintLifecycleHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_lifecycle_not_loaded",),
                details={"loaded": False},
            )

        try:
            records = self._registry.list_records()
            self._validate_single_active_invariants(records)
        except VoiceprintLifecycleConflictError:
            return VoiceprintLifecycleHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_single_active_violation",),
                details={"loaded": True},
            )
        except VoiceprintRegistryRecordNotFoundError:
            return VoiceprintLifecycleHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_lifecycle_record_missing",),
                details={"loaded": True},
            )
        except VoiceprintRegistryValidationError:
            return VoiceprintLifecycleHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voiceprint_lifecycle_not_loaded",),
                details={"loaded": False},
            )

        return VoiceprintLifecycleHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_lifecycle_ready",),
            details={"loaded": True, "record_count": len(records)},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise VoiceprintLifecycleNotLoadedError("voiceprint_lifecycle_not_loaded")

    def _assert_transition_allowed(
        self,
        current: VoiceprintLifecycleState,
        target: VoiceprintLifecycleState,
    ) -> None:
        allowed: dict[VoiceprintLifecycleState, set[VoiceprintLifecycleState]] = {
            VoiceprintLifecycleState.PENDING: {
                VoiceprintLifecycleState.ACTIVE,
                VoiceprintLifecycleState.FAILED,
            },
            VoiceprintLifecycleState.ACTIVE: {
                VoiceprintLifecycleState.INACTIVE,
                VoiceprintLifecycleState.SUPERSEDED,
                VoiceprintLifecycleState.DELETED,
            },
            VoiceprintLifecycleState.INACTIVE: {
                VoiceprintLifecycleState.ACTIVE,
                VoiceprintLifecycleState.DELETED,
            },
            VoiceprintLifecycleState.SUPERSEDED: {
                VoiceprintLifecycleState.DELETED,
            },
            VoiceprintLifecycleState.FAILED: {
                VoiceprintLifecycleState.DELETED,
            },
            VoiceprintLifecycleState.DELETED: set(),
        }

        if target not in allowed[current]:
            raise VoiceprintLifecycleInvalidTransitionError("voiceprint_lifecycle_invalid_transition")

    def _ensure_no_other_active_conflict(
        self,
        record: VoiceprintRecord,
        *,
        excluded_ids: set[str] | None = None,
    ) -> None:
        excluded = excluded_ids or set()
        for existing in self._registry.list_records():
            if existing.voiceprint_id.value == record.voiceprint_id.value:
                continue
            if existing.voiceprint_id.value in excluded:
                continue
            if not existing.active:
                continue
            same_subject = existing.subject_id == record.subject_id
            same_lineage = existing.lineage.lineage_root_id == record.lineage.lineage_root_id
            if same_subject or same_lineage:
                raise VoiceprintLifecycleConflictError("voiceprint_single_active_violation")

    def _validate_single_active_invariants(self, records: tuple[VoiceprintRecord, ...]) -> None:
        active_by_subject: dict[str, str] = {}
        active_by_lineage: dict[str, str] = {}

        for record in records:
            if not record.active:
                continue
            subject = record.subject_id.value
            lineage = record.lineage.lineage_root_id.value
            if subject in active_by_subject or lineage in active_by_lineage:
                raise VoiceprintLifecycleConflictError("voiceprint_single_active_violation")
            active_by_subject[subject] = record.voiceprint_id.value
            active_by_lineage[lineage] = record.voiceprint_id.value
