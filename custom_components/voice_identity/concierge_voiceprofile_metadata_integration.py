"""Concierge VoiceProfile metadata integration over public Voice Identity contracts.

This module provides Concierge-facing VoiceProfile metadata and readiness
projections by consuming VI-115 and VI-118 read-only contracts.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from re import compile as re_compile
from typing import Protocol

from .concierge_discovery_integration import (
    ConciergeDiscoveryFailureCategory,
    ConciergeDiscoveryIntegration,
    ConciergeDiscoveryRequest,
    ConciergeDiscoveryState,
)
from .health_state import HealthState
from .voiceprint_status_metadata_operation import (
    GetVoiceprintMetadataRequest,
    GetVoiceprintOperationFailureResult,
    GetVoiceprintStatusFailureCategory,
    GetVoiceprintStatusOperation,
)

_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")
_DEFAULT_CACHE_MAX_ENTRIES = 128
_DEFAULT_CACHE_TTL_SECONDS = 180


class ConciergeVoiceProfileState(StrEnum):
    """Concierge-facing VoiceProfile state model."""

    UNAVAILABLE = "unavailable"
    NOT_ENROLLED = "not_enrolled"
    ENROLLED = "enrolled"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class ConciergeVoiceProfileReadiness(StrEnum):
    """Concierge-facing metadata readiness outcomes."""

    READY = "ready"
    ENROLLMENT_REQUIRED = "enrollment_required"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class ConciergeVoiceProfileFailureCategory(StrEnum):
    """Safe failure taxonomy for VoiceProfile metadata integration."""

    VOICE_PROFILE_UNAVAILABLE = "voice_profile_unavailable"
    VOICE_PROFILE_NOT_FOUND = "voice_profile_not_found"
    METADATA_UNAVAILABLE = "metadata_unavailable"
    ENROLLMENT_REQUIRED = "enrollment_required"
    VOICE_IDENTITY_UNAVAILABLE = "voice_identity_unavailable"
    VOICE_IDENTITY_INCOMPATIBLE = "voice_identity_incompatible"
    OPERATION_NOT_LOADED = "operation_not_loaded"
    OPERATION_INTERNAL_ERROR = "operation_internal_error"


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileRequest:
    """Public request for Concierge VoiceProfile metadata integration."""

    voiceprint_id: str | None = None
    metadata_contract_version: int = 1
    requested_discovery_contract_version: int = 1
    requested_discovery_schema_version: int = 1
    force_refresh: bool = False
    correlation_id: str | None = None
    request_metadata: dict[str, bool | int | float | str | None] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        voiceprint_id: str | None = None,
        metadata_contract_version: int = 1,
        requested_discovery_contract_version: int = 1,
        requested_discovery_schema_version: int = 1,
        force_refresh: bool = False,
        correlation_id: str | None = None,
        request_metadata: dict[str, bool | int | float | str | None] | None = None,
    ) -> ConciergeVoiceProfileRequest:
        normalized_id = voiceprint_id.strip() if isinstance(voiceprint_id, str) else None
        if normalized_id == "":
            normalized_id = None
        return cls(
            voiceprint_id=normalized_id,
            metadata_contract_version=metadata_contract_version,
            requested_discovery_contract_version=requested_discovery_contract_version,
            requested_discovery_schema_version=requested_discovery_schema_version,
            force_refresh=force_refresh,
            correlation_id=_safe_token(correlation_id, None),
            request_metadata=_sanitize_metadata(request_metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileVersionInformation:
    """Safe version information consumed by Concierge."""

    service_name: str
    service_version: str
    discovery_contract_version: int
    metadata_schema_version: int
    capability_discovery_schema_version: int
    status_contract_version: int
    supported_contract_versions: tuple[int, ...]
    supported_schema_versions: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileProjection:
    """Concierge-facing VoiceProfile metadata projection."""

    voiceprint_id: str | None
    active: bool
    lifecycle_state: str
    enrollment_state: str
    version_information: ConciergeVoiceProfileVersionInformation
    profile_ready: bool
    superseded: bool
    created_timestamp: str | None
    updated_timestamp: str | None
    state: ConciergeVoiceProfileState
    readiness: ConciergeVoiceProfileReadiness


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileSuccessResult:
    """Successful VoiceProfile metadata projection result."""

    success: bool
    projection: ConciergeVoiceProfileProjection
    cache_hit: bool
    diagnostics: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileFailureResult:
    """Safe failure contract with fallback VoiceProfile projection."""

    success: bool
    failure_category: ConciergeVoiceProfileFailureCategory
    reason_code: str
    projection: ConciergeVoiceProfileProjection
    diagnostics: dict[str, bool | int | float | str | None]
    completed_at: str


ConciergeVoiceProfileResult = ConciergeVoiceProfileSuccessResult | ConciergeVoiceProfileFailureResult


@dataclass(slots=True, frozen=True)
class ConciergeVoiceProfileIntegrationHealth:
    """Health projection for runtime integration registration."""

    state: HealthState
    reason_codes: tuple[str, ...]
    details: dict[str, bool | int | float | str | None]


@dataclass(slots=True, frozen=True)
class _CacheKey:
    voiceprint_id: str
    metadata_contract_version: int
    discovery_contract_version: int
    discovery_schema_version: int
    discovery_state: str
    service_available: bool
    service_compatible: bool


@dataclass(slots=True, frozen=True)
class _CacheEntry:
    projection: ConciergeVoiceProfileProjection
    stored_at: datetime


class _CacheBackend(Protocol):
    def get(self, key: _CacheKey, *, now: datetime) -> ConciergeVoiceProfileProjection | None:
        pass

    def set(self, key: _CacheKey, projection: ConciergeVoiceProfileProjection, *, now: datetime) -> None:
        pass

    def clear(self) -> None:
        pass


class _InMemoryCacheBackend:
    """Bounded in-memory cache for Concierge VoiceProfile metadata projections."""

    def __init__(self, *, max_entries: int, ttl_seconds: int) -> None:
        self._max_entries = max(1, max_entries)
        self._ttl_seconds = max(1, ttl_seconds)
        self._entries: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()

    def get(self, key: _CacheKey, *, now: datetime) -> ConciergeVoiceProfileProjection | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if int((now - entry.stored_at).total_seconds()) > self._ttl_seconds:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry.projection

    def set(self, key: _CacheKey, projection: ConciergeVoiceProfileProjection, *, now: datetime) -> None:
        self._entries[key] = _CacheEntry(projection=projection, stored_at=now)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


class ConciergeVoiceProfileMetadataIntegration:
    """Concierge-facing integration for VoiceProfile metadata and readiness."""

    def __init__(
        self,
        *,
        status_operation: GetVoiceprintStatusOperation | None,
        discovery_integration: ConciergeDiscoveryIntegration | None,
        cache_backend: _CacheBackend | None = None,
        cache_max_entries: int = _DEFAULT_CACHE_MAX_ENTRIES,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._status_operation = status_operation
        self._discovery_integration = discovery_integration
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
        status_operation: GetVoiceprintStatusOperation | None,
        discovery_integration: ConciergeDiscoveryIntegration | None,
        cache_backend: _CacheBackend | None = None,
        cache_max_entries: int = _DEFAULT_CACHE_MAX_ENTRIES,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> ConciergeVoiceProfileMetadataIntegration:
        return cls(
            status_operation=status_operation,
            discovery_integration=discovery_integration,
            cache_backend=cache_backend,
            cache_max_entries=cache_max_entries,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    async def resolve(self, request: ConciergeVoiceProfileRequest) -> ConciergeVoiceProfileResult:
        if not self._loaded:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                projection=_unavailable_projection(request=request),
                diagnostics={"loaded": False},
            )

        now = datetime.now(timezone.utc)

        if self._discovery_integration is None:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_unavailable_projection(request=request),
                diagnostics={"loaded": True, "service_available": False},
            )

        try:
            discovery_result = await self._discovery_integration.discover(
                ConciergeDiscoveryRequest.create(
                    requested_contract_version=request.requested_discovery_contract_version,
                    requested_schema_version=request.requested_discovery_schema_version,
                    force_refresh=request.force_refresh,
                    correlation_id=request.correlation_id,
                    request_metadata=request.request_metadata,
                )
            )
        except Exception:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                projection=_unknown_projection(request=request),
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

        if not discovery_result.success:
            if discovery_result.failure_category is ConciergeDiscoveryFailureCategory.OPERATION_NOT_LOADED:
                return self._failure(
                    failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_NOT_LOADED,
                    reason_code="operation_not_loaded",
                    projection=_unavailable_projection(request=request),
                    diagnostics={"loaded": False},
                )
            if discovery_result.failure_category is ConciergeDiscoveryFailureCategory.OPERATION_INTERNAL_ERROR:
                return self._failure(
                    failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_INTERNAL_ERROR,
                    reason_code="operation_internal_error",
                    projection=_unknown_projection(request=request),
                    diagnostics={"loaded": True, "error": "operation_internal_error"},
                )
            if discovery_result.failure_category is ConciergeDiscoveryFailureCategory.VOICE_IDENTITY_INCOMPATIBLE:
                return self._failure(
                    failure_category=ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_INCOMPATIBLE,
                    reason_code="voice_identity_incompatible",
                    projection=_incompatible_projection(
                        request=request,
                        version_information=_version_info_from_discovery(
                            discovery_result.projection.version_information
                        ),
                    ),
                    diagnostics={"loaded": True, "service_compatible": False},
                )
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_unavailable_projection(request=request),
                diagnostics={"loaded": True, "service_available": False},
            )

        discovery_projection = discovery_result.projection
        version_information = _version_info_from_discovery(discovery_projection.version_information)
        cache_key = _cache_key(request=request, discovery_projection=discovery_projection)

        if not discovery_projection.service_available:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_IDENTITY_UNAVAILABLE,
                reason_code="voice_identity_unavailable",
                projection=_unavailable_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True, "service_available": False},
            )

        if discovery_projection.discovery_state is ConciergeDiscoveryState.INCOMPATIBLE:
            projection = _incompatible_projection(request=request, version_information=version_information)
            return ConciergeVoiceProfileSuccessResult(
                success=True,
                projection=projection,
                cache_hit=False,
                diagnostics={"loaded": True, "service_compatible": False},
            )

        if not request.force_refresh:
            try:
                cached = self._cache_backend.get(cache_key, now=now)
            except Exception:
                cached = None
            if cached is not None:
                return ConciergeVoiceProfileSuccessResult(
                    success=True,
                    projection=cached,
                    cache_hit=True,
                    diagnostics={"loaded": True, "cache": "hit"},
                )

        if not _metadata_capability_available(discovery_projection):
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_PROFILE_UNAVAILABLE,
                reason_code="voice_profile_unavailable",
                projection=_unavailable_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True, "capability_available": False},
            )

        if self._status_operation is None:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_PROFILE_UNAVAILABLE,
                reason_code="voice_profile_unavailable",
                projection=_unavailable_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True, "operation_available": False},
            )

        if request.voiceprint_id is None:
            projection = _not_enrolled_projection(request=request, version_information=version_information)
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.ENROLLMENT_REQUIRED,
                reason_code="enrollment_required",
                projection=projection,
                diagnostics={"loaded": True, "voiceprint_present": False},
            )

        try:
            metadata_result = await self._status_operation.get_metadata(
                GetVoiceprintMetadataRequest.create(
                    voiceprint_id=request.voiceprint_id,
                    compatibility_version=request.metadata_contract_version,
                    correlation_id=request.correlation_id,
                    request_metadata=request.request_metadata,
                )
            )
        except Exception:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                projection=_unknown_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

        if isinstance(metadata_result, GetVoiceprintOperationFailureResult):
            return self._map_metadata_failure(
                request=request,
                failure=metadata_result,
                version_information=version_information,
            )

        state = _state_from_metadata(
            lifecycle_state=metadata_result.metadata.lifecycle_state,
            active=metadata_result.metadata.active,
            superseded=metadata_result.metadata.superseded,
        )
        readiness = _readiness_from_state(
            state=state,
            discovery_state=discovery_projection.discovery_state,
            service_available=discovery_projection.service_available,
        )
        projection = ConciergeVoiceProfileProjection(
            voiceprint_id=metadata_result.metadata.voiceprint_id,
            active=metadata_result.metadata.active,
            lifecycle_state=metadata_result.metadata.lifecycle_state,
            enrollment_state=_enrollment_state(state),
            version_information=version_information,
            profile_ready=readiness is ConciergeVoiceProfileReadiness.READY,
            superseded=metadata_result.metadata.superseded,
            created_timestamp=metadata_result.metadata.created_timestamp,
            updated_timestamp=metadata_result.metadata.updated_timestamp,
            state=state,
            readiness=readiness,
        )

        try:
            self._cache_backend.set(cache_key, projection, now=now)
            cache_status = "miss"
        except Exception:
            cache_status = "unavailable"

        return ConciergeVoiceProfileSuccessResult(
            success=True,
            projection=projection,
            cache_hit=False,
            diagnostics={
                "loaded": True,
                "cache": cache_status,
                "profile_ready": projection.profile_ready,
            },
        )

    async def validate_health(self) -> ConciergeVoiceProfileIntegrationHealth:
        if not self._loaded:
            return ConciergeVoiceProfileIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("operation_not_loaded",),
                details={"loaded": False},
            )

        if self._discovery_integration is None or self._status_operation is None:
            return ConciergeVoiceProfileIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voice_profile_unavailable",),
                details={"loaded": True},
            )

        discovery = await self._discovery_integration.discover(
            ConciergeDiscoveryRequest.create(force_refresh=True)
        )
        if not discovery.success or not discovery.projection.service_available:
            return ConciergeVoiceProfileIntegrationHealth(
                state=HealthState.UNAVAILABLE,
                reason_codes=("voice_identity_unavailable",),
                details={"loaded": True, "service_available": False},
            )

        if discovery.projection.discovery_state is ConciergeDiscoveryState.INCOMPATIBLE:
            return ConciergeVoiceProfileIntegrationHealth(
                state=HealthState.DEGRADED,
                reason_codes=("voice_identity_incompatible",),
                details={"loaded": True, "service_compatible": False},
            )

        if not _metadata_capability_available(discovery.projection):
            return ConciergeVoiceProfileIntegrationHealth(
                state=HealthState.DEGRADED,
                reason_codes=("voice_profile_unavailable",),
                details={"loaded": True, "capability_available": False},
            )

        return ConciergeVoiceProfileIntegrationHealth(
            state=HealthState.HEALTHY,
            reason_codes=("concierge_voiceprofile_metadata_ready",),
            details={"loaded": True, "service_available": True},
        )

    def clear(self) -> None:
        self._loaded = False
        self._cleared = True
        try:
            self._cache_backend.clear()
        except Exception:
            pass

    @property
    def cleared(self) -> bool:
        return self._cleared

    def _map_metadata_failure(
        self,
        *,
        request: ConciergeVoiceProfileRequest,
        failure: GetVoiceprintOperationFailureResult,
        version_information: ConciergeVoiceProfileVersionInformation,
    ) -> ConciergeVoiceProfileFailureResult:
        if failure.failure_category is GetVoiceprintStatusFailureCategory.VOICEPRINT_NOT_FOUND:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.VOICE_PROFILE_NOT_FOUND,
                reason_code="voice_profile_not_found",
                projection=_not_enrolled_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True},
            )

        if failure.failure_category in {
            GetVoiceprintStatusFailureCategory.METADATA_UNAVAILABLE,
            GetVoiceprintStatusFailureCategory.STATUS_UNAVAILABLE,
        }:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.METADATA_UNAVAILABLE,
                reason_code="metadata_unavailable",
                projection=_unknown_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True},
            )

        if failure.failure_category is GetVoiceprintStatusFailureCategory.OPERATION_NOT_LOADED:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_NOT_LOADED,
                reason_code="operation_not_loaded",
                projection=_unavailable_projection(request=request, version_information=version_information),
                diagnostics={"loaded": False},
            )

        if failure.failure_category is GetVoiceprintStatusFailureCategory.OPERATION_INTERNAL_ERROR:
            return self._failure(
                failure_category=ConciergeVoiceProfileFailureCategory.OPERATION_INTERNAL_ERROR,
                reason_code="operation_internal_error",
                projection=_unknown_projection(request=request, version_information=version_information),
                diagnostics={"loaded": True, "error": "operation_internal_error"},
            )

        return self._failure(
            failure_category=ConciergeVoiceProfileFailureCategory.VOICE_PROFILE_UNAVAILABLE,
            reason_code="voice_profile_unavailable",
            projection=_unknown_projection(request=request, version_information=version_information),
            diagnostics={"loaded": True},
        )

    def _failure(
        self,
        *,
        failure_category: ConciergeVoiceProfileFailureCategory,
        reason_code: str,
        projection: ConciergeVoiceProfileProjection,
        diagnostics: dict[str, bool | int | float | str | None],
    ) -> ConciergeVoiceProfileFailureResult:
        return ConciergeVoiceProfileFailureResult(
            success=False,
            failure_category=failure_category,
            reason_code=_safe_token(reason_code, failure_category.value) or failure_category.value,
            projection=projection,
            diagnostics=_sanitize_metadata(diagnostics),
            completed_at=_utcnow_iso(),
        )


def _cache_key(
    *,
    request: ConciergeVoiceProfileRequest,
    discovery_projection,
) -> _CacheKey:
    return _CacheKey(
        voiceprint_id=request.voiceprint_id or "none",
        metadata_contract_version=request.metadata_contract_version,
        discovery_contract_version=request.requested_discovery_contract_version,
        discovery_schema_version=request.requested_discovery_schema_version,
        discovery_state=discovery_projection.discovery_state.value,
        service_available=discovery_projection.service_available,
        service_compatible=discovery_projection.service_compatible,
    )


def _metadata_capability_available(discovery_projection) -> bool:
    required = {"voiceprint_status", "metadata_retrieval"}
    supported = set(discovery_projection.supported_capabilities)
    enabled = set(discovery_projection.enabled_capabilities)
    return required.issubset(supported) and required.issubset(enabled)


def _version_info_from_discovery(source) -> ConciergeVoiceProfileVersionInformation:
    return ConciergeVoiceProfileVersionInformation(
        service_name=source.service_name,
        service_version=source.service_version,
        discovery_contract_version=source.discovery_contract_version,
        metadata_schema_version=source.metadata_schema_version,
        capability_discovery_schema_version=source.capability_discovery_schema_version,
        status_contract_version=source.status_contract_version,
        supported_contract_versions=source.supported_contract_versions,
        supported_schema_versions=source.supported_schema_versions,
    )


def _state_from_metadata(*, lifecycle_state: str, active: bool, superseded: bool) -> ConciergeVoiceProfileState:
    normalized = lifecycle_state.strip().lower()
    if normalized == "active" and active:
        return ConciergeVoiceProfileState.ACTIVE
    if normalized == "superseded" or superseded:
        return ConciergeVoiceProfileState.SUPERSEDED
    if normalized in {"retired", "deleted"}:
        return ConciergeVoiceProfileState.RETIRED
    if normalized in {"pending", "inactive"}:
        return ConciergeVoiceProfileState.ENROLLED
    return ConciergeVoiceProfileState.UNKNOWN


def _readiness_from_state(
    *,
    state: ConciergeVoiceProfileState,
    discovery_state: ConciergeDiscoveryState,
    service_available: bool,
) -> ConciergeVoiceProfileReadiness:
    if not service_available:
        return ConciergeVoiceProfileReadiness.UNAVAILABLE
    if discovery_state is ConciergeDiscoveryState.INCOMPATIBLE:
        return ConciergeVoiceProfileReadiness.INCOMPATIBLE
    if state is ConciergeVoiceProfileState.ACTIVE:
        return ConciergeVoiceProfileReadiness.READY
    if state in {
        ConciergeVoiceProfileState.NOT_ENROLLED,
        ConciergeVoiceProfileState.SUPERSEDED,
        ConciergeVoiceProfileState.RETIRED,
    }:
        return ConciergeVoiceProfileReadiness.ENROLLMENT_REQUIRED
    return ConciergeVoiceProfileReadiness.UNKNOWN


def _enrollment_state(state: ConciergeVoiceProfileState) -> str:
    if state in {ConciergeVoiceProfileState.ACTIVE, ConciergeVoiceProfileState.ENROLLED}:
        return "complete"
    if state in {
        ConciergeVoiceProfileState.NOT_ENROLLED,
        ConciergeVoiceProfileState.SUPERSEDED,
        ConciergeVoiceProfileState.RETIRED,
    }:
        return "required"
    return "unknown"


def _default_version_info() -> ConciergeVoiceProfileVersionInformation:
    return ConciergeVoiceProfileVersionInformation(
        service_name="voice_identity",
        service_version="unknown",
        discovery_contract_version=0,
        metadata_schema_version=0,
        capability_discovery_schema_version=0,
        status_contract_version=0,
        supported_contract_versions=(),
        supported_schema_versions=(),
    )


def _unavailable_projection(
    *,
    request: ConciergeVoiceProfileRequest,
    version_information: ConciergeVoiceProfileVersionInformation | None = None,
) -> ConciergeVoiceProfileProjection:
    return ConciergeVoiceProfileProjection(
        voiceprint_id=request.voiceprint_id,
        active=False,
        lifecycle_state="unavailable",
        enrollment_state="unknown",
        version_information=version_information or _default_version_info(),
        profile_ready=False,
        superseded=False,
        created_timestamp=None,
        updated_timestamp=None,
        state=ConciergeVoiceProfileState.UNAVAILABLE,
        readiness=ConciergeVoiceProfileReadiness.UNAVAILABLE,
    )


def _incompatible_projection(
    *,
    request: ConciergeVoiceProfileRequest,
    version_information: ConciergeVoiceProfileVersionInformation,
) -> ConciergeVoiceProfileProjection:
    return ConciergeVoiceProfileProjection(
        voiceprint_id=request.voiceprint_id,
        active=False,
        lifecycle_state="incompatible",
        enrollment_state="unknown",
        version_information=version_information,
        profile_ready=False,
        superseded=False,
        created_timestamp=None,
        updated_timestamp=None,
        state=ConciergeVoiceProfileState.UNAVAILABLE,
        readiness=ConciergeVoiceProfileReadiness.INCOMPATIBLE,
    )


def _not_enrolled_projection(
    *,
    request: ConciergeVoiceProfileRequest,
    version_information: ConciergeVoiceProfileVersionInformation,
) -> ConciergeVoiceProfileProjection:
    return ConciergeVoiceProfileProjection(
        voiceprint_id=request.voiceprint_id,
        active=False,
        lifecycle_state="not_enrolled",
        enrollment_state="required",
        version_information=version_information,
        profile_ready=False,
        superseded=False,
        created_timestamp=None,
        updated_timestamp=None,
        state=ConciergeVoiceProfileState.NOT_ENROLLED,
        readiness=ConciergeVoiceProfileReadiness.ENROLLMENT_REQUIRED,
    )


def _unknown_projection(
    *,
    request: ConciergeVoiceProfileRequest,
    version_information: ConciergeVoiceProfileVersionInformation | None = None,
) -> ConciergeVoiceProfileProjection:
    return ConciergeVoiceProfileProjection(
        voiceprint_id=request.voiceprint_id,
        active=False,
        lifecycle_state="unknown",
        enrollment_state="unknown",
        version_information=version_information or _default_version_info(),
        profile_ready=False,
        superseded=False,
        created_timestamp=None,
        updated_timestamp=None,
        state=ConciergeVoiceProfileState.UNKNOWN,
        readiness=ConciergeVoiceProfileReadiness.UNKNOWN,
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