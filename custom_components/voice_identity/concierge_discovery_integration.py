"""Concierge discovery integration over Voice Identity public discovery contracts.

This module provides a Concierge-facing read model for availability,
compatibility, health, and capability visibility by consuming VI-117 contracts.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile
from typing import Protocol

from .capability_discovery_operation import (
    CompatibilityDiscoveryRequest,
    CompatibilityStatus,
    DiscoveryFailureResult,
    GetCapabilitiesFailureCategory,
    GetCapabilitiesOperation,
    GetCapabilitiesRequest,
    GetVersionDiscoveryRequest,
)
from .health_state import HealthState

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")
_DEFAULT_CACHE_MAX_ENTRIES = 8
_DEFAULT_CACHE_TTL_SECONDS = 120

_CAPABILITY_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "voiceprint_operation_generate": ("generate_voiceprint",),
    "voiceprint_operation_status_metadata": (
        "voiceprint_status",
        "metadata_retrieval",
    ),
    "voiceprint_operation_delete_supersede": (
        "delete_voiceprint",
        "supersede_voiceprint",
    ),
    "capability_discovery_operation": (
        "capability_discovery",
        "version_discovery",
    ),
}


class ConciergeDiscoveryState(StrEnum):
    """Concierge-facing discovery lifecycle states."""

    UNAVAILABLE = "unavailable"
    DISCOVERED = "discovered"
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    DEGRADED = "degraded"
    HEALTHY = "healthy"


class ConciergeDiscoveryFailureCategory(StrEnum):
    """Safe failure taxonomy for Concierge discovery integration."""

    VOICE_IDENTITY_UNAVAILABLE = "voice_identity_unavailable"
    VOICE_IDENTITY_INCOMPATIBLE = "voice_identity_incompatible"
    CAPABILITY_DISCOVERY_FAILED = "capability_discovery_failed"
    COMPATIBILITY_EVALUATION_FAILED = "compatibility_evaluation_failed"
    CACHE_UNAVAILABLE = "cache_unavailable"
    OPERATION_NOT_LOADED = "operation_not_loaded"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


@dataclass(slots=True, frozen=True)
class ConciergeDiscoveryRequest:
    """Public request for Concierge discovery integration."""

    requested_contract_version: int = 1
    requested_schema_version: int = 1
    force_refresh: bool = False
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        requested_contract_version: int = 1,
        requested_schema_version: int = 1,
        force_refresh: bool = False,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> ConciergeDiscoveryRequest:
        return cls(
            requested_contract_version=requested_contract_version,
            requested_schema_version=requested_schema_version,
            force_refresh=force_refresh,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class ConciergeVersionInformation:
    """Safe version projection consumed by Concierge."""

    service_name: str
    service_version: str
    discovery_contract_version: int
    metadata_schema_version: int
    capability_discovery_schema_version: int
    status_contract_version: int
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class ConciergeCompatibilityProjection:
    """Safe compatibility projection consumed by Concierge."""

    compatibility_status: str
    upgrade_guidance: str
    requested_contract_version: int | None
    requested_schema_version: int | None
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class ConciergeDiscoveryProjection:
    """Concierge-facing discovery projection for feature gating."""

    discovery_state: ConciergeDiscoveryState
    service_available: bool
    service_healthy: bool
    service_compatible: bool
    supported_capabilities: tuple[str, ...]
    enabled_capabilities: tuple[str, ...]
    compatibility: ConciergeCompatibilityProjection
    version_information: ConciergeVersionInformation


@dataclass(slots=True, frozen=True)
class ConciergeDiscoverySuccessResult:
    """Successful discovery projection for Concierge consumption."""

    success: bool
    projection: ConciergeDiscoveryProjection
    cache_hit: bool
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class ConciergeDiscoveryFailureResult:
    """Safe failure contract with fallback projection for graceful degradation."""

    success: bool
    failure_category: ConciergeDiscoveryFailureCategory
    reason_code: str
    projection: ConciergeDiscoveryProjection
    diagnostics: dict[str, bool | int | float | str | None]
    completed_at: str


ConciergeDiscoveryResult = ConciergeDiscoverySuccessResult | ConciergeDiscoveryFailureResult


@dataclass(slots=True, frozen=True)
class ConciergeDiscoveryIntegrationHealth:
    """Health projection for runtime integration registration."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class _CacheKey:
    requested_contract_version: int
    requested_schema_version: int


@dataclass(slots=True, frozen=True)
class _CacheEntry:
    projection: ConciergeDiscoveryProjection
    stored_at: datetime


class _CacheBackend(Protocol):
    def get(self, key: _CacheKey, *, now: datetime) -> ConciergeDiscoveryProjection | None:
        pass

    def set(self, key: _CacheKey, projection: ConciergeDiscoveryProjection, *, now: datetime) -> None:
        pass

    def clear(self) -> None:
        pass


class _InMemoryCacheBackend:
    """Bounded in-memory cache for Concierge discovery projections."""

    def __init__(self, *, max_entries: int, ttl_seconds: int) -> None:
        bounded_entries = max(1, max_entries)
        bounded_ttl = max(1, ttl_seconds)
        self._max_entries = bounded_entries
        self._ttl_seconds = bounded_ttl
        self._entries: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()

    def get(self, key: _CacheKey, *, now: datetime) -> ConciergeDiscoveryProjection | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        age_seconds = int((now - entry.stored_at).total_seconds())
        if age_seconds > self._ttl_seconds:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry.projection

    def set(self, key: _CacheKey, projection: ConciergeDiscoveryProjection, *, now: datetime) -> None:
        self._entries[key] = _CacheEntry(projection=projection, stored_at=now)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


class ConciergeDiscoveryIntegration:
    """Concierge-facing discovery integration built on VI-117 contracts."""

    def __init__(
        self,
        *,
        capabilities_operation: GetCapabilitiesOperation | None,
        cache_backend: _CacheBackend | None = None,
        cache_max_entries: int = _DEFAULT_CACHE_MAX_ENTRIES,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._capabilities_operation = capabilities_operation
        self._cache_backend = cache_backend or _InMemoryCacheBackend(
            max_entries=cache_max_entries,
            ttl_seconds=cache_ttl_seconds,
        )
        self._loaded = True
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        capabilities_operation: GetCapabilitiesOperation | None,
        cache_backend: _CacheBackend | None = None,
        cache_max_entries: int = _DEFAULT_CACHE_MAX_ENTRIES,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> ConciergeDiscoveryIntegration:
        return cls(
            capabilities_operation=capabilities_operation,
            cache_backend=cache_backend,
            cache_max_entries=cache_max_entries,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    async def discover(self, request: ConciergeDiscoveryRequest) -> ConciergeDiscoveryResult:
        if not self._loaded:
            return self._failure(
                failure_category=ConciergeDiscoveryFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                projection=_unavailable_projection(
                    request=request,
                    compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                    upgrade_guidance="service_not_loaded",
                ),
                diagnostics={"loaded": False},
            )

        cache_key = _CacheKey(
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
        )
        now = datetime.now(timezone.utc)
        if not request.force_refresh:
            try:
                cached = self._cache_backend.get(cache_key, now=now)
            except Exception:
                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.CACHE_UNAVAILABLE,
                    reason_code="cache_unavailable",
                    projection=_unavailable_projection(
                        request=request,
                        compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                        upgrade_guidance="cache_unavailable",
                    ),
                    diagnostics={"loaded": True, "cache": "unavailable"},
                )
            if cached is not None:
                return ConciergeDiscoverySuccessResult(
                    success=True,
                    projection=cached,
                    cache_hit=True,
                    diagnostics={"loaded": True, "cache": "hit"},
                )

        if self._capabilities_operation is None:
            return self._failure(
                failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_unavailable_projection(
                    request=request,
                    compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                    upgrade_guidance="service_unavailable",
                ),
                diagnostics={"loaded": True, "service_available": False},
            )

        try:
            version_result = await self._capabilities_operation.get_versions(
                GetVersionDiscoveryRequest.create(
                    requested_contract_version=request.requested_contract_version,
                    requested_schema_version=request.requested_schema_version,
                    correlation_id=request.correlation_id,
                    request_metadata=request.request_metadata,
                )
            )

            if isinstance(version_result, DiscoveryFailureResult):
                if version_result.failure_category in {
                    GetCapabilitiesFailureCategory.COMPATIBILITY_VERSION_UNSUPPORTED,
                    GetCapabilitiesFailureCategory.SCHEMA_VERSION_UNSUPPORTED,
                }:
                    return self._failure(
                        failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
                        reason_code="voice_identity_incompatible",
                        projection=_incompatible_projection(
                            request=request,
                            compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                            upgrade_guidance="select_supported_versions",
                        ),
                        diagnostics={"loaded": True, "service_available": True},
                    )

                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.CAPABILITY_DISCOVERY_FAILED,
                    reason_code="capability_discovery_failed",
                    projection=_unavailable_projection(
                        request=request,
                        compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                        upgrade_guidance="retry_discovery",
                    ),
                    diagnostics={"loaded": True, "service_available": False},
                )

            compatibility_result = await self._capabilities_operation.evaluate_compatibility(
                CompatibilityDiscoveryRequest.create(
                    requested_contract_version=request.requested_contract_version,
                    requested_schema_version=request.requested_schema_version,
                    correlation_id=request.correlation_id,
                    request_metadata=request.request_metadata,
                )
            )
            if isinstance(compatibility_result, DiscoveryFailureResult):
                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.COMPATIBILITY_EVALUATION_FAILED,
                    reason_code="compatibility_evaluation_failed",
                    projection=_discovered_projection(
                        request=request,
                        version_information=_version_information_from_result(version_result),
                    ),
                    diagnostics={"loaded": True, "service_available": True},
                )

            capabilities_result = await self._capabilities_operation.execute(
                GetCapabilitiesRequest.create(
                    requested_contract_version=request.requested_contract_version,
                    requested_schema_version=request.requested_schema_version,
                    correlation_id=request.correlation_id,
                    request_metadata=request.request_metadata,
                )
            )
            if isinstance(capabilities_result, DiscoveryFailureResult):
                if capabilities_result.failure_category in {
                    GetCapabilitiesFailureCategory.COMPATIBILITY_VERSION_UNSUPPORTED,
                    GetCapabilitiesFailureCategory.SCHEMA_VERSION_UNSUPPORTED,
                }:
                    return self._failure(
                        failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
                        reason_code="voice_identity_incompatible",
                        projection=_incompatible_projection(
                            request=request,
                            compatibility_status=compatibility_result.compatibility_status.value,
                            upgrade_guidance=compatibility_result.compatibility_details.upgrade_guidance,
                        ),
                        diagnostics={"loaded": True, "service_available": True},
                    )

                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.CAPABILITY_DISCOVERY_FAILED,
                    reason_code="capability_discovery_failed",
                    projection=_degraded_projection(
                        request=request,
                        version_information=_version_information_from_result(version_result),
                    ),
                    diagnostics={"loaded": True, "service_available": True},
                )

            operation_health = await self._capabilities_operation.validate_health()
            service_healthy = operation_health.state is HealthState.HEALTHY
            compatibility_status = compatibility_result.compatibility_status
            service_compatible = compatibility_status is CompatibilityStatus.COMPATIBLE
            supported_capabilities, enabled_capabilities = _project_concierge_capabilities(capabilities_result)

            projection = ConciergeDiscoveryProjection(
                discovery_state=_derive_discovery_state(
                    service_available=True,
                    service_healthy=service_healthy,
                    compatibility_status=compatibility_status,
                ),
                service_available=True,
                service_healthy=service_healthy,
                service_compatible=service_compatible,
                supported_capabilities=supported_capabilities,
                enabled_capabilities=enabled_capabilities,
                compatibility=ConciergeCompatibilityProjection(
                    compatibility_status=compatibility_status.value,
                    upgrade_guidance=compatibility_result.compatibility_details.upgrade_guidance,
                    requested_contract_version=compatibility_result.compatibility_details.requested_contract_version,
                    requested_schema_version=compatibility_result.compatibility_details.requested_schema_version,
                    supported_contract_versions=compatibility_result.compatibility_details.supported_contract_versions,
                    supported_schema_versions=compatibility_result.compatibility_details.supported_schema_versions,
                ),
                version_information=_version_information_from_result(version_result),
            )

            if compatibility_status is CompatibilityStatus.UNSUPPORTED:
                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
                    reason_code="voice_identity_incompatible",
                    projection=projection,
                    diagnostics={"loaded": True, "service_available": True, "service_compatible": False},
                )

            try:
                self._cache_backend.set(cache_key, projection, now=now)
            except Exception:
                return self._failure(
                    failure_category=ConciergeDiscoveryFailureCategory.CACHE_UNAVAILABLE,
                    reason_code="cache_unavailable",
                    projection=projection,
                    diagnostics={"loaded": True, "cache": "unavailable"},
                )

            return ConciergeDiscoverySuccessResult(
                success=True,
                projection=projection,
                cache_hit=False,
                diagnostics={
                    "loaded": True,
                    "cache": "miss",
                    "supported_capability_count": len(supported_capabilities),
                    "enabled_capability_count": len(enabled_capabilities),
                },
            )
        except Exception:
            return self._failure(
                failure_category=ConciergeDiscoveryFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                projection=_unavailable_projection(
                    request=request,
                    compatibility_status=CompatibilityStatus.UNSUPPORTED.value,
                    upgrade_guidance="retry_discovery",
                ),
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

    async def validate_health(self) -> ConciergeDiscoveryIntegrationHealth:
        if not self._loaded:
            return ConciergeDiscoveryIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_not_loaded",),
                details={"loaded": False},
            )

        if self._capabilities_operation is None:
            return ConciergeDiscoveryIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voice_identity_unavailable",),
                details={"loaded": True, "service_available": False},
            )

        result = await self.discover(ConciergeDiscoveryRequest.create(force_refresh=True))
        if not result.success:
            if result.failure_category is ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE:
                return ConciergeDiscoveryIntegrationHealth(
                    state=HealthState.DEGRADED,
                    reason_codes=("voice_identity_incompatible",),
                    details={"loaded": True, "service_compatible": False},
                )
            return ConciergeDiscoveryIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=(result.reason_code,),
                details={"loaded": True, "service_available": result.projection.service_available},
            )

        if result.projection.discovery_state is ConciergeDiscoveryState.HEALTHY:
            return ConciergeDiscoveryIntegrationHealth(
                state=HealthState.HEALTHY,
                reason_codes=("concierge_discovery_ready",),
                details={"loaded": True, "service_available": True},
            )

        if result.projection.discovery_state is ConciergeDiscoveryState.DEGRADED:
            return ConciergeDiscoveryIntegrationHealth(
                state=HealthState.DEGRADED,
                reason_codes=("voice_identity_degraded",),
                details={"loaded": True, "service_available": True},
            )

        return ConciergeDiscoveryIntegrationHealth(
            state=HealthState.UNAVAILABLE,
            reason_codes=("voice_identity_unavailable",),
            details={"loaded": True, "service_available": False},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True
        try:
            self._cache_backend.clear()
        except Exception:
            # Clear should always be safe for unload.
            pass

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _failure(
        self,
        *,
        failure_category: ConciergeDiscoveryFailureCategory,
        reason_code: str,
        projection: ConciergeDiscoveryProjection,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> ConciergeDiscoveryFailureResult:
        return ConciergeDiscoveryFailureResult(
            success=False,
            failure_category=failure_category,
            reason_code=_safe_token(reason_code, failure_category.value) or failure_category.value,
            projection=projection,
            diagnostics=_sanitize_metadata(diagnostics),
            completed_at=_utcnow_iso(),
        )


def _project_concierge_capabilities(
    result,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    supported: set[str] = set()
    enabled: set[str] = set()
    for item in result.capabilities:
        aliases = _CAPABILITY_ALIAS_MAP.get(item.capability_name, ())
        if item.supported:
            supported.update(aliases)
        if item.enabled:
            enabled.update(aliases)
    return tuple(sorted(supported)), tuple(sorted(enabled))


def _derive_discovery_state(
    *,
    service_available: bool,
    service_healthy: bool,
    compatibility_status: CompatibilityStatus,
) -> ConciergeDiscoveryState:
    if not service_available:
        return ConciergeDiscoveryState.UNAVAILABLE

    if compatibility_status is CompatibilityStatus.UNSUPPORTED:
        return ConciergeDiscoveryState.INCOMPATIBLE

    if compatibility_status is CompatibilityStatus.PARTIALLY_COMPATIBLE:
        return ConciergeDiscoveryState.DEGRADED

    if compatibility_status is CompatibilityStatus.COMPATIBLE and service_healthy:
        return ConciergeDiscoveryState.HEALTHY

    if compatibility_status is CompatibilityStatus.COMPATIBLE:
        return ConciergeDiscoveryState.COMPATIBLE

    return ConciergeDiscoveryState.DEGRADED


def _discovered_projection(
    *,
    request: ConciergeDiscoveryRequest,
    version_information: ConciergeVersionInformation,
) -> ConciergeDiscoveryProjection:
    return ConciergeDiscoveryProjection(
        discovery_state=ConciergeDiscoveryState.DISCOVERED,
        service_available=True,
        service_healthy=False,
        service_compatible=False,
        supported_capabilities=(),
        enabled_capabilities=(),
        compatibility=ConciergeCompatibilityProjection(
            compatibility_status=CompatibilityStatus.PARTIALLY_COMPATIBLE.value,
            upgrade_guidance="retry_compatibility_evaluation",
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            supported_contract_versions=version_information.supported_contract_versions,
            supported_schema_versions=version_information.supported_schema_versions,
        ),
        version_information=version_information,
    )


def _version_information_from_result(result) -> ConciergeVersionInformation:
    return ConciergeVersionInformation(
        service_name=result.service_name,
        service_version=result.service_version,
        discovery_contract_version=result.discovery_contract_version,
        metadata_schema_version=result.metadata_schema_version,
        capability_discovery_schema_version=result.capability_discovery_schema_version,
        status_contract_version=result.status_contract_version,
        supported_contract_versions=result.supported_contract_versions,
        supported_schema_versions=result.supported_schema_versions,
    )


def _unavailable_projection(
    *,
    request: ConciergeDiscoveryRequest,
    compatibility_status: str,
    upgrade_guidance: str,
) -> ConciergeDiscoveryProjection:
    return ConciergeDiscoveryProjection(
        discovery_state=ConciergeDiscoveryState.UNAVAILABLE,
        service_available=False,
        service_healthy=False,
        service_compatible=False,
        supported_capabilities=(),
        enabled_capabilities=(),
        compatibility=ConciergeCompatibilityProjection(
            compatibility_status=compatibility_status,
            upgrade_guidance=upgrade_guidance,
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            supported_contract_versions=(),
            supported_schema_versions=(),
        ),
        version_information=ConciergeVersionInformation(
            service_name="voice_identity",
            service_version="unknown",
            discovery_contract_version=0,
            metadata_schema_version=0,
            capability_discovery_schema_version=0,
            status_contract_version=0,
            supported_contract_versions=(),
            supported_schema_versions=(),
        ),
    )


def _incompatible_projection(
    *,
    request: ConciergeDiscoveryRequest,
    compatibility_status: str,
    upgrade_guidance: str,
) -> ConciergeDiscoveryProjection:
    return ConciergeDiscoveryProjection(
        discovery_state=ConciergeDiscoveryState.INCOMPATIBLE,
        service_available=True,
        service_healthy=False,
        service_compatible=False,
        supported_capabilities=(),
        enabled_capabilities=(),
        compatibility=ConciergeCompatibilityProjection(
            compatibility_status=compatibility_status,
            upgrade_guidance=upgrade_guidance,
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            supported_contract_versions=(),
            supported_schema_versions=(),
        ),
        version_information=ConciergeVersionInformation(
            service_name="voice_identity",
            service_version="unknown",
            discovery_contract_version=0,
            metadata_schema_version=0,
            capability_discovery_schema_version=0,
            status_contract_version=0,
            supported_contract_versions=(),
            supported_schema_versions=(),
        ),
    )


def _degraded_projection(
    *,
    request: ConciergeDiscoveryRequest,
    version_information: ConciergeVersionInformation,
) -> ConciergeDiscoveryProjection:
    return ConciergeDiscoveryProjection(
        discovery_state=ConciergeDiscoveryState.DEGRADED,
        service_available=True,
        service_healthy=False,
        service_compatible=False,
        supported_capabilities=(),
        enabled_capabilities=(),
        compatibility=ConciergeCompatibilityProjection(
            compatibility_status=CompatibilityStatus.PARTIALLY_COMPATIBLE.value,
            upgrade_guidance="retry_discovery",
            requested_contract_version=request.requested_contract_version,
            requested_schema_version=request.requested_schema_version,
            supported_contract_versions=version_information.supported_contract_versions,
            supported_schema_versions=version_information.supported_schema_versions,
        ),
        version_information=version_information,
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
    return any(
        token in key
        for token in ("token", "secret", "key", "path", "url", "config", "object", "ref")
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()