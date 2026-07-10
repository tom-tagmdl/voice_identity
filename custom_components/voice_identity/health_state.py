"""Health state engine for Voice Identity integration.

Capability discovery and health evaluation are separate concerns. This engine
evaluates health of currently wired components and produces deterministic
read-only snapshots with safe machine-readable reason codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import compile as re_compile
from typing import Mapping, Sequence

from .capability_registry import VoiceIdentityCapabilityRegistry
from .configuration import (
    VoiceIdentityConfigMigrationRequiredError,
    VoiceIdentityConfigurationError,
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigurationNotLoadedError,
)

_REASON_CODE_PATTERN = re_compile(r"^[a-z0-9_]+$")
_DETAIL_KEY_PATTERN = re_compile(r"^[a-z0-9_]+$")
_DETAIL_STRING_VALUE_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class HealthState(StrEnum):
    """Health states supported by the engine."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    MIGRATION_REQUIRED = "migration_required"


class HealthReasonCode(StrEnum):
    """Safe machine-readable reason codes."""

    SERVICE_NOT_LOADED = "service_not_loaded"
    CONFIGURATION_INVALID = "configuration_invalid"
    CONFIGURATION_MIGRATION_REQUIRED = "configuration_migration_required"
    CAPABILITY_NOT_IMPLEMENTED = "capability_not_implemented"
    CAPABILITY_DISABLED = "capability_disabled"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


@dataclass(slots=True, frozen=True)
class ComponentHealthReport:
    """Health report for one component."""

    component: str
    required: bool
    state: HealthState
    reason_codes: tuple[str, ...]
    details: Mapping[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class HealthSnapshot:
    """Read-only aggregate health snapshot."""

    state: HealthState
    reason_codes: tuple[str, ...]
    components: tuple[ComponentHealthReport, ...]


class VoiceIdentityHealthStateError(Exception):
    """Base exception for health state failures."""


class VoiceIdentityUnsafeReasonCodeError(VoiceIdentityHealthStateError):
    """Raised when reason codes violate safety format."""


class VoiceIdentityUnsafeDetailsError(VoiceIdentityHealthStateError):
    """Raised when public health details violate safety format."""


class VoiceIdentityHealthStateEngine:
    """Deterministic health state engine for Voice Identity runtime."""

    def __init__(self) -> None:
        self._component_reports: dict[str, ComponentHealthReport] = {}

    @classmethod
    def from_foundation(
        cls,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        capability_registry: VoiceIdentityCapabilityRegistry,
        runtime_loaded: bool,
    ) -> VoiceIdentityHealthStateEngine:
        """Construct and evaluate foundation health inputs."""
        engine = cls()
        engine.evaluate_foundation(
            config_manager=config_manager,
            capability_registry=capability_registry,
            runtime_loaded=runtime_loaded,
        )
        return engine

    def evaluate_foundation(
        self,
        *,
        config_manager: VoiceIdentityConfigurationManager,
        capability_registry: VoiceIdentityCapabilityRegistry,
        runtime_loaded: bool,
    ) -> HealthSnapshot:
        """Evaluate current foundation health inputs and return aggregate snapshot."""
        if runtime_loaded:
            self.set_component(
                component="integration_runtime",
                required=True,
                state=HealthState.HEALTHY,
            )
        else:
            self.set_component(
                component="integration_runtime",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.SERVICE_NOT_LOADED,),
            )

        self._evaluate_configuration_manager(config_manager)
        self._evaluate_capability_registry(capability_registry)
        return self.snapshot()

    def set_component(
        self,
        *,
        component: str,
        required: bool,
        state: HealthState,
        reason_codes: Sequence[str | HealthReasonCode] = (),
        details: Mapping[str, bool | int | float | str | None] | None = None,
    ) -> None:
        """Set or replace one component health report."""
        normalized_component = component.strip()
        if not normalized_component:
            raise VoiceIdentityHealthStateError("Component name must not be empty.")

        report = ComponentHealthReport(
            component=normalized_component,
            required=required,
            state=state,
            reason_codes=_normalize_reason_codes(reason_codes),
            details=_normalize_details(details),
        )
        self._component_reports[normalized_component] = report

    def snapshot(self) -> HealthSnapshot:
        """Return deterministic aggregate snapshot across all registered components."""
        reports = tuple(self._sorted_reports())
        state = _aggregate_state(reports)
        reason_codes = _aggregate_reason_codes(reports)
        return HealthSnapshot(
            state=state,
            reason_codes=reason_codes,
            components=reports,
        )

    def clear(self) -> None:
        """Clear all component reports."""
        self._component_reports.clear()

    def _sorted_reports(self) -> list[ComponentHealthReport]:
        return [self._component_reports[name] for name in sorted(self._component_reports)]

    def _evaluate_configuration_manager(
        self,
        config_manager: VoiceIdentityConfigurationManager,
    ) -> None:
        try:
            _ = config_manager.config
        except VoiceIdentityConfigMigrationRequiredError:
            self.set_component(
                component="configuration_manager",
                required=True,
                state=HealthState.MIGRATION_REQUIRED,
                reason_codes=(HealthReasonCode.CONFIGURATION_MIGRATION_REQUIRED,),
            )
            return
        except VoiceIdentityConfigurationNotLoadedError:
            self.set_component(
                component="configuration_manager",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.SERVICE_NOT_LOADED,),
            )
            return
        except VoiceIdentityConfigurationError:
            self.set_component(
                component="configuration_manager",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.CONFIGURATION_INVALID,),
            )
            return

        self.set_component(
            component="configuration_manager",
            required=True,
            state=HealthState.HEALTHY,
        )

    def _evaluate_capability_registry(
        self,
        capability_registry: VoiceIdentityCapabilityRegistry,
    ) -> None:
        if not capability_registry.supports("capability_registry"):
            self.set_component(
                component="capability_registry",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.CAPABILITY_NOT_IMPLEMENTED,),
            )
            return

        status = capability_registry.status("capability_registry")
        if status is None:
            self.set_component(
                component="capability_registry",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.DEPENDENCY_UNAVAILABLE,),
            )
            return

        if not status.enabled:
            self.set_component(
                component="capability_registry",
                required=True,
                state=HealthState.UNAVAILABLE,
                reason_codes=(HealthReasonCode.CAPABILITY_DISABLED,),
            )
            return

        self.set_component(
            component="capability_registry",
            required=True,
            state=HealthState.HEALTHY,
        )


def _aggregate_state(reports: Sequence[ComponentHealthReport]) -> HealthState:
    required_reports = [report for report in reports if report.required]
    optional_reports = [report for report in reports if not report.required]

    if any(report.state is HealthState.MIGRATION_REQUIRED for report in required_reports):
        return HealthState.MIGRATION_REQUIRED

    if any(report.state is HealthState.UNAVAILABLE for report in required_reports):
        return HealthState.UNAVAILABLE

    if any(report.state is HealthState.DEGRADED for report in required_reports + optional_reports):
        return HealthState.DEGRADED

    if any(report.state in {HealthState.MIGRATION_REQUIRED, HealthState.UNAVAILABLE} for report in optional_reports):
        return HealthState.DEGRADED

    return HealthState.HEALTHY


def _aggregate_reason_codes(reports: Sequence[ComponentHealthReport]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []

    for report in reports:
        for reason_code in report.reason_codes:
            if reason_code not in seen:
                seen.add(reason_code)
                ordered.append(reason_code)

    return tuple(ordered)


def _normalize_reason_codes(reason_codes: Sequence[str | HealthReasonCode]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for reason_code in reason_codes:
        value = reason_code.value if isinstance(reason_code, HealthReasonCode) else reason_code
        if not _REASON_CODE_PATTERN.fullmatch(value):
            raise VoiceIdentityUnsafeReasonCodeError(
                "Reason codes must match ^[a-z0-9_]+$ and contain no secrets or free text."
            )
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return tuple(normalized)


def _normalize_details(
    details: Mapping[str, bool | int | float | str | None] | None,
) -> dict[str, bool | int | float | str | None]:
    if details is None:
        return {}

    normalized: dict[str, bool | int | float | str | None] = {}
    for key, value in details.items():
        if not _DETAIL_KEY_PATTERN.fullmatch(key):
            raise VoiceIdentityUnsafeDetailsError(
                "Detail keys must match ^[a-z0-9_]+$ and be machine-safe."
            )

        if isinstance(value, str) and not _DETAIL_STRING_VALUE_PATTERN.fullmatch(value):
            raise VoiceIdentityUnsafeDetailsError(
                "Detail string values must be safe machine tokens, not free text or paths."
            )

        if not isinstance(value, (bool, int, float, str, type(None))):
            raise VoiceIdentityUnsafeDetailsError(
                "Detail values must be primitive safe types only."
            )

        normalized[key] = value

    return normalized
