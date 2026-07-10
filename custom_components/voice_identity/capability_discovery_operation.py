"""Capability and version discovery operations for public service consumers.

This module provides a read-only public discovery surface over the authoritative
capability registry and exposes deterministic compatibility projections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile

from .capability_registry import CapabilityMaturity, VoiceIdentityCapabilityRegistry
from .health_state import HealthState

_DISCOVERY_CONTRACT_VERSION_CURRENT = 1
_SUPPORTED_CONTRACT_VERSIONS = (_DISCOVERY_CONTRACT_VERSION_CURRENT,)
_DISCOVERY_SCHEMA_VERSION_CURRENT = 1
_SUPPORTED_SCHEMA_VERSIONS = (_DISCOVERY_SCHEMA_VERSION_CURRENT,)
_METADATA_SCHEMA_VERSION_CURRENT = 1
_STATUS_CONTRACT_VERSION_CURRENT = 1
_SERVICE_NAME = "voice_identity"
_SERVICE_VERSION = "0.1.0"
_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")


class CompatibilityStatus(StrEnum):
    """Compatibility evaluation statuses."""

    COMPATIBLE = "compatible"
    PARTIALLY_COMPATIBLE = "partially_compatible"
    UNSUPPORTED = "unsupported"


class GetCapabilitiesFailureCategory(StrEnum):
    """Safe failure taxonomy for discovery operations."""

    COMPATIBILITY_VERSION_UNSUPPORTED = "compatibility_version_unsupported"
    SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"
    CAPABILITY_REGISTRY_UNAVAILABLE = "capability_registry_unavailable"
    DISCOVERY_UNAVAILABLE = "discovery_unavailable"
    OPERATION_NOT_LOADED = "operation_not_loaded"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


@dataclass(slots=True, frozen=True)
class GetCapabilitiesRequest:
    """Public request contract for capability discovery."""

    requested_contract_version: int = _DISCOVERY_CONTRACT_VERSION_CURRENT
    requested_schema_version: int = _DISCOVERY_SCHEMA_VERSION_CURRENT
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        requested_contract_version: int = _DISCOVERY_CONTRACT_VERSION_CURRENT,
        requested_schema_version: int = _DISCOVERY_SCHEMA_VERSION_CURRENT,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> GetCapabilitiesRequest:
        return cls(
            requested_contract_version=requested_contract_version,
            requested_schema_version=requested_schema_version,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class GetVersionDiscoveryRequest:
    """Public request contract for version discovery."""

    requested_contract_version: int = _DISCOVERY_CONTRACT_VERSION_CURRENT
    requested_schema_version: int = _DISCOVERY_SCHEMA_VERSION_CURRENT
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        requested_contract_version: int = _DISCOVERY_CONTRACT_VERSION_CURRENT,
        requested_schema_version: int = _DISCOVERY_SCHEMA_VERSION_CURRENT,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> GetVersionDiscoveryRequest:
        return cls(
            requested_contract_version=requested_contract_version,
            requested_schema_version=requested_schema_version,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class CompatibilityDiscoveryRequest:
    """Public request contract for compatibility evaluation."""

    requested_contract_version: int | None = _DISCOVERY_CONTRACT_VERSION_CURRENT
    requested_schema_version: int | None = _DISCOVERY_SCHEMA_VERSION_CURRENT
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        requested_contract_version: int | None = _DISCOVERY_CONTRACT_VERSION_CURRENT,
        requested_schema_version: int | None = _DISCOVERY_SCHEMA_VERSION_CURRENT,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> CompatibilityDiscoveryRequest:
        return cls(
            requested_contract_version=requested_contract_version,
            requested_schema_version=requested_schema_version,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class CapabilityProjection:
    """Stable public projection for one capability."""

    capability_name: str
    supported: bool
    implemented: bool
    enabled: bool
    description: str
    contract_version: int
    schema_version: int


@dataclass(slots=True, frozen=True)
class CompatibilityDetails:
    """Compatibility details for consumer negotiation."""

    requested_contract_version: int | None
    requested_schema_version: int | None
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]
    upgrade_guidance: str


@dataclass(slots=True, frozen=True)
class GetCapabilitiesSuccessResult:
    """Public success contract for capability discovery."""

    success: bool
    service_name: str
    service_version: str
    discovery_contract_version: int
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]
    capabilities: tuple[CapabilityProjection, ...]
    compatibility_status: CompatibilityStatus
    compatibility_details: CompatibilityDetails
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class GetVersionDiscoverySuccessResult:
    """Public success contract for version and schema discovery."""

    success: bool
    service_name: str
    service_version: str
    discovery_contract_version: int
    metadata_schema_version: int
    capability_discovery_schema_version: int
    status_contract_version: int
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]
    compatibility_status: CompatibilityStatus
    compatibility_details: CompatibilityDetails
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class CompatibilityDiscoveryResult:
    """Public success contract for compatibility evaluation."""

    success: bool
    service_name: str
    service_version: str
    compatibility_status: CompatibilityStatus
    compatibility_details: CompatibilityDetails
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class DiscoveryFailureResult:
    """Public failure contract for discovery operations."""

    success: bool
    failure_category: GetCapabilitiesFailureCategory
    reason_code: str
    requested_contract_version: int | None
    requested_schema_version: int | None
    diagnostics: dict[str, bool | int | float | str | None]
    completed_at: str


GetCapabilitiesResult = GetCapabilitiesSuccessResult | DiscoveryFailureResult
GetVersionDiscoveryResult = GetVersionDiscoverySuccessResult | DiscoveryFailureResult


@dataclass(slots=True, frozen=True)
class CapabilityDiscoveryOperationHealth:
    """Readiness projection for capability discovery operations."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


class GetCapabilitiesOperation:
    """Read-only operation for capabilities, versions, and compatibility."""

    def __init__(self, *, capability_registry: VoiceIdentityCapabilityRegistry) -> None:
        self._capability_registry = capability_registry
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        capability_registry: VoiceIdentityCapabilityRegistry,
    ) -> GetCapabilitiesOperation:
        return cls(capability_registry=capability_registry)

    async def execute(self, request: GetCapabilitiesRequest) -> GetCapabilitiesResult:
        if not self._loaded:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": False},
            )

        contract_error = _contract_failure(requested_contract_version=request.requested_contract_version)
        if contract_error is not None:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.COMPATIBILITY_VERSION_UNSUPPORTED,
                reason_code="compatibility_version_unsupported",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics=contract_error,
            )

        schema_error = _schema_failure(requested_schema_version=request.requested_schema_version)
        if schema_error is not None:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.SCHEMA_VERSION_UNSUPPORTED,
                reason_code="schema_version_unsupported",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics=schema_error,
            )

        if not self._capability_registry.supports("capability_registry"):
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.CAPABILITY_REGISTRY_UNAVAILABLE,
                reason_code="capability_registry_unavailable",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": True},
            )

        try:
            snapshot = self._capability_registry.snapshot()
            capabilities = tuple(
                CapabilityProjection(
                    capability_name=status.descriptor.name,
                    supported=status.supported,
                    implemented=status.descriptor.maturity is CapabilityMaturity.IMPLEMENTED,
                    enabled=status.enabled,
                    description=status.descriptor.description,
                    contract_version=status.descriptor.introduced_config_schema_version,
                    schema_version=snapshot.registry_schema_version,
                )
                for status in snapshot.capabilities
            )
            compatibility_details = _compatibility_details(
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
            )

            return GetCapabilitiesSuccessResult(
                success=True,
                service_name=_SERVICE_NAME,
                service_version=_SERVICE_VERSION,
                discovery_contract_version=_DISCOVERY_CONTRACT_VERSION_CURRENT,
                supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
                supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
                capabilities=capabilities,
                compatibility_status=CompatibilityStatus.COMPATIBLE,
                compatibility_details=compatibility_details,
                diagnostics={
                    "loaded": True,
                    "capability_count": len(capabilities),
                    "supported_count": len(tuple(item for item in capabilities if item.supported)),
                    "implemented_count": len(tuple(item for item in capabilities if item.implemented)),
                    "enabled_count": len(tuple(item for item in capabilities if item.enabled)),
                },
            )
        except Exception:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def get_versions(self, request: GetVersionDiscoveryRequest) -> GetVersionDiscoveryResult:
        if not self._loaded:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": False},
            )

        contract_error = _contract_failure(requested_contract_version=request.requested_contract_version)
        if contract_error is not None:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.COMPATIBILITY_VERSION_UNSUPPORTED,
                reason_code="compatibility_version_unsupported",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics=contract_error,
            )

        schema_error = _schema_failure(requested_schema_version=request.requested_schema_version)
        if schema_error is not None:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.SCHEMA_VERSION_UNSUPPORTED,
                reason_code="schema_version_unsupported",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics=schema_error,
            )

        try:
            compatibility_details = _compatibility_details(
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
            )
            return GetVersionDiscoverySuccessResult(
                success=True,
                service_name=_SERVICE_NAME,
                service_version=_SERVICE_VERSION,
                discovery_contract_version=_DISCOVERY_CONTRACT_VERSION_CURRENT,
                metadata_schema_version=_METADATA_SCHEMA_VERSION_CURRENT,
                capability_discovery_schema_version=_DISCOVERY_SCHEMA_VERSION_CURRENT,
                status_contract_version=_STATUS_CONTRACT_VERSION_CURRENT,
                supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
                supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
                compatibility_status=CompatibilityStatus.COMPATIBLE,
                compatibility_details=compatibility_details,
                diagnostics={"loaded": True},
            )
        except Exception:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.DISCOVERY_UNAVAILABLE,
                reason_code="discovery_unavailable",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": True},
            )

    async def evaluate_compatibility(
        self,
        request: CompatibilityDiscoveryRequest,
    ) -> CompatibilityDiscoveryResult | DiscoveryFailureResult:
        if not self._loaded:
            return self._build_failure(
                failure_category=GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                diagnostics={"loaded": False},
            )

        status, details = _compatibility_status(request)
        return CompatibilityDiscoveryResult(
            success=True,
            service_name=_SERVICE_NAME,
            service_version=_SERVICE_VERSION,
            compatibility_status=status,
            compatibility_details=details,
            diagnostics={"loaded": True},
        )

    async def validate_health(self) -> CapabilityDiscoveryOperationHealth:
        if not self._loaded:
            return CapabilityDiscoveryOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_not_loaded",),
                details={"loaded": False},
            )

        try:
            if not self._capability_registry.supports("capability_registry"):
                return CapabilityDiscoveryOperationHealth(
                    state=HealthState.UNAVAILABLE,
                    reason_codes=("capability_registry_unavailable",),
                    details={"loaded": True},
                )
            _ = self._capability_registry.snapshot()
        except Exception:
            return CapabilityDiscoveryOperationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_internal_error",),
                details={"loaded": True},
            )

        return CapabilityDiscoveryOperationHealth(
            state=HealthState.HEALTHY,
            reason_codes=("capability_discovery_ready", "version_discovery_ready"),
            details={"loaded": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _build_failure(
        self,
        *,
        failure_category: GetCapabilitiesFailureCategory,
        reason_code: str,
        requested_contract_version: int | None,
        requested_schema_version: int | None,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> DiscoveryFailureResult:
        return DiscoveryFailureResult(
            success=False,
            failure_category=failure_category,
            reason_code=_safe_token(reason_code, failure_category.value) or failure_category.value,
            requested_contract_version=requested_contract_version,
            requested_schema_version=requested_schema_version,
            diagnostics=_sanitize_metadata(diagnostics),
            completed_at=_utcnow_iso(),
        )


def _contract_failure(*, requested_contract_version: int) -> dict[str, bool | int | float | str | None] | None:
    if requested_contract_version in _SUPPORTED_CONTRACT_VERSIONS:
        return None
    return {
        "loaded": True,
        "requested_contract_version": requested_contract_version,
        "supported_contract_version": _DISCOVERY_CONTRACT_VERSION_CURRENT,
    }


def _schema_failure(*, requested_schema_version: int) -> dict[str, bool | int | float | str | None] | None:
    if requested_schema_version in _SUPPORTED_SCHEMA_VERSIONS:
        return None
    return {
        "loaded": True,
        "requested_schema_version": requested_schema_version,
        "supported_schema_version": _DISCOVERY_SCHEMA_VERSION_CURRENT,
    }


def _compatibility_details(
    *,
    requested_contract_version: int | None,
    requested_schema_version: int | None,
) -> CompatibilityDetails:
    return CompatibilityDetails(
        requested_contract_version=requested_contract_version,
        requested_schema_version=requested_schema_version,
        supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
        supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
        upgrade_guidance="no_action_required",
    )


def _compatibility_status(
    request: CompatibilityDiscoveryRequest,
) -> tuple[CompatibilityStatus, CompatibilityDetails]:
    contract_supported = (
        request.requested_contract_version in _SUPPORTED_CONTRACT_VERSIONS
        if request.requested_contract_version is not None
        else False
    )
    schema_supported = (
        request.requested_schema_version in _SUPPORTED_SCHEMA_VERSIONS
        if request.requested_schema_version is not None
        else False
    )

    if contract_supported and schema_supported:
        return (
            CompatibilityStatus.COMPATIBLE,
            CompatibilityDetails(
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
                supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
                upgrade_guidance="no_action_required",
            ),
        )

    if contract_supported or schema_supported:
        return (
            CompatibilityStatus.PARTIALLY_COMPATIBLE,
            CompatibilityDetails(
                requested_contract_version=request.requested_contract_version,
                requested_schema_version=request.requested_schema_version,
                supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
                supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
                upgrade_guidance="upgrade_recommended",
            ),
        )

    return (
        CompatibilityStatus.UNSUPPORTED,
        CompatibilityDetails(
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            supported_contract_versions=_SUPPORTED_CONTRACT_VERSIONS,
            supported_schema_versions=_SUPPORTED_SCHEMA_VERSIONS,
            upgrade_guidance="select_supported_versions",
        ),
    )


def _sanitize_metadata(
    values: dict[str, bool | int | float | str | None],
) -> dict[str, bool | int | float | str | None]:
    sanitized: dict[str, bool | int | float | str | None] = {}
    for key, value in values.items():
        safe_key = _safe_token(key, "meta")
        if _is_sensitive_key(safe_key):
            continue
        if isinstance(value, str):
            safe_value = _safe_metadata_value(value)
            if safe_value:
                sanitized[safe_key] = safe_value
        elif isinstance(value, (bool, int, float, type(None))):
            sanitized[safe_key] = value
    return sanitized


def _safe_token(value: str | None, fallback: str | None) -> str | None:
    if value is not None:
        normalized = value.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized):
            return normalized
    if fallback is not None:
        normalized_fallback = fallback.strip().lower()
        if _SAFE_TOKEN_PATTERN.fullmatch(normalized_fallback):
            return normalized_fallback
    return None


def _safe_metadata_value(value: str) -> str:
    normalized = _safe_token(value, "")
    if not normalized:
        return ""
    if "http" in normalized or "/" in normalized or "\\" in normalized:
        return ""
    if "token" in normalized or "secret" in normalized or "key" in normalized:
        return ""
    if "traceback" in normalized or "exception" in normalized:
        return ""
    return normalized


def _is_sensitive_key(key: str) -> bool:
    return any(token in key for token in ("token", "secret", "key", "path", "url", "config", "object", "ref"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
