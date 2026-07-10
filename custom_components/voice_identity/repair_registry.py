"""Central repair definition registry for Voice Identity.

The registry is the authoritative source for deterministic recommendation lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics_sanitizer import normalize_reason_code
from .repair_definitions import RepairDefinition, default_repair_definitions


class VoiceIdentityRepairRegistryError(Exception):
    """Base exception for repair registry failures."""


class VoiceIdentityRepairDefinitionDuplicateError(VoiceIdentityRepairRegistryError):
    """Raised when attempting to register a duplicate repair id."""


@dataclass(slots=True, frozen=True)
class RepairRegistrySnapshot:
    """Deterministic snapshot of registered repair definitions."""

    definitions: tuple[RepairDefinition, ...]


class VoiceIdentityRepairRegistry:
    """Registry for deterministic reason-code to repair-definition mapping."""

    def __init__(self) -> None:
        self._definitions: dict[str, RepairDefinition] = {}
        self._reason_code_index: dict[str, tuple[str, ...]] = {}

    @classmethod
    def with_defaults(cls) -> VoiceIdentityRepairRegistry:
        """Construct a registry preloaded with built-in repairs."""
        registry = cls()
        for definition in default_repair_definitions():
            registry.register(definition)
        return registry

    def register(self, definition: RepairDefinition) -> None:
        """Register one repair definition and index its reason codes."""
        if definition.repair_id in self._definitions:
            raise VoiceIdentityRepairDefinitionDuplicateError(
                f"Repair definition '{definition.repair_id}' is already registered."
            )

        self._definitions[definition.repair_id] = definition
        for reason_code in definition.supported_reason_codes:
            normalized = normalize_reason_code(reason_code)
            existing = self._reason_code_index.get(normalized, ())
            self._reason_code_index[normalized] = tuple(sorted((*existing, definition.repair_id)))

    def resolve_by_reason_code(self, reason_code: str | None) -> tuple[RepairDefinition, ...]:
        """Resolve deterministic recommendations for one reason code."""
        normalized = normalize_reason_code(reason_code)
        repair_ids = self._reason_code_index.get(normalized, ())
        return tuple(self._definitions[repair_id] for repair_id in repair_ids)

    def resolve_by_reason_codes(self, reason_codes: tuple[str, ...]) -> tuple[RepairDefinition, ...]:
        """Resolve deterministic recommendations for a reason-code set."""
        resolved_ids: set[str] = set()
        for reason_code in reason_codes:
            normalized = normalize_reason_code(reason_code)
            for repair_id in self._reason_code_index.get(normalized, ()):  # pragma: no branch
                resolved_ids.add(repair_id)

        return tuple(self._definitions[repair_id] for repair_id in sorted(resolved_ids))

    def snapshot(self) -> RepairRegistrySnapshot:
        """Return deterministic snapshot of all registered definitions."""
        return RepairRegistrySnapshot(
            definitions=tuple(self._definitions[repair_id] for repair_id in sorted(self._definitions)),
        )
