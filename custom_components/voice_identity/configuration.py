"""Configuration manager for Voice Identity integration.

This module provides a single authoritative runtime configuration source that
loads from Home Assistant config entries and exposes validated typed models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .const import (
    CONFIG_SCHEMA_VERSION_CURRENT,
    CONFIG_SCHEMA_VERSION_MINIMUM_SUPPORTED,
    CONF_ATTRIBUTION,
    CONF_CLEANUP,
    CONF_CLEANUP_ENABLED,
    CONF_CONFIG_SCHEMA_VERSION,
    CONF_DEFAULT_CONFIDENCE_THRESHOLD,
    CONF_DIAGNOSTICS,
    CONF_DIAGNOSTICS_ALLOWLIST_ONLY,
    CONF_DIAGNOSTICS_ENABLED,
    CONF_ENABLE_EXPERIMENTAL_MODELS,
    CONF_ENABLE_REPAIRS,
    CONF_ENABLE_RUNTIME_ATTRIBUTION,
    CONF_FEATURE_FLAGS,
    CONF_GENERATION,
    CONF_INCLUDE_RUNTIME_METRICS,
    CONF_MAX_CACHED_VOICEPRINTS,
    CONF_MAX_CANDIDATE_SCOPE_SIZE,
    CONF_MAX_SAMPLE_COUNT,
    CONF_MIN_SAMPLE_COUNT,
    CONF_MODEL_PREFERENCE,
    CONF_QUALITY_THRESHOLD,
    CONF_RECONCILE_ON_STARTUP,
    CONF_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
    CONF_SERVICE,
    CONF_SERVICE_ENABLED,
    CONF_SESSION_TIMEOUT_SECONDS,
    CONF_STARTUP_TIMEOUT_SECONDS,
    CONF_STORAGE,
    CONF_STORAGE_BASE_PATH,
    CONF_STORAGE_ENCRYPTION_REQUIRED,
    CONF_STORAGE_PROVIDER,
    CONF_SUPPORTED_MODELS,
    DEFAULT_CLEANUP_ENABLED,
    DEFAULT_DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DIAGNOSTICS_ALLOWLIST_ONLY,
    DEFAULT_DIAGNOSTICS_ENABLED,
    DEFAULT_ENABLE_EXPERIMENTAL_MODELS,
    DEFAULT_ENABLE_REPAIRS,
    DEFAULT_ENABLE_RUNTIME_ATTRIBUTION,
    DEFAULT_INCLUDE_RUNTIME_METRICS,
    DEFAULT_MAX_CACHED_VOICEPRINTS,
    DEFAULT_MAX_CANDIDATE_SCOPE_SIZE,
    DEFAULT_MAX_SAMPLE_COUNT,
    DEFAULT_MIN_SAMPLE_COUNT,
    DEFAULT_MODEL_PREFERENCE,
    DEFAULT_QUALITY_THRESHOLD,
    DEFAULT_RECONCILE_ON_STARTUP,
    DEFAULT_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
    DEFAULT_SERVICE_ENABLED,
    DEFAULT_SESSION_TIMEOUT_SECONDS,
    DEFAULT_STARTUP_TIMEOUT_SECONDS,
    DEFAULT_STORAGE_BASE_PATH,
    DEFAULT_STORAGE_ENCRYPTION_REQUIRED,
    DEFAULT_STORAGE_PROVIDER,
    DEFAULT_SUPPORTED_MODELS,
)


class VoiceIdentityConfigurationError(Exception):
    """Base exception for configuration manager failures."""


class VoiceIdentityConfigurationNotLoadedError(VoiceIdentityConfigurationError):
    """Raised when configuration is accessed before load."""


class VoiceIdentityConfigurationValidationError(VoiceIdentityConfigurationError):
    """Raised when input configuration is invalid."""


class VoiceIdentityUnsupportedConfigVersionError(VoiceIdentityConfigurationValidationError):
    """Raised when configuration schema version is newer than supported."""


class VoiceIdentityConfigMigrationRequiredError(VoiceIdentityConfigurationValidationError):
    """Raised when configuration schema version is too old."""


class SupportsConfigEntry(Protocol):
    """Minimal config entry surface required by configuration manager."""

    entry_id: str
    data: Mapping[str, Any]
    options: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class ServiceConfiguration:
    """Service-level runtime controls."""

    enabled: bool
    startup_timeout_seconds: int
    max_cached_voiceprints: int


@dataclass(slots=True, frozen=True)
class StorageConfiguration:
    """Storage provider controls for provider-owned artifacts."""

    provider: str
    base_path: str
    encryption_required: bool


@dataclass(slots=True, frozen=True)
class GenerationConfiguration:
    """Generation pipeline defaults and quality bounds."""

    model_preference: str
    min_sample_count: int
    max_sample_count: int
    quality_threshold: float
    supported_models: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class CleanupConfiguration:
    """Lifecycle cleanup controls."""

    enabled: bool
    session_timeout_seconds: int
    reconcile_on_startup: bool


@dataclass(slots=True, frozen=True)
class DiagnosticsConfiguration:
    """Diagnostics behavior controls with privacy guardrails."""

    enabled: bool
    allowlist_only: bool
    include_runtime_metrics: bool


@dataclass(slots=True, frozen=True)
class FeatureFlagsConfiguration:
    """Capability gating and feature flag controls."""

    enable_runtime_attribution: bool
    enable_repairs: bool
    enable_experimental_models: bool


@dataclass(slots=True, frozen=True)
class AttributionConfiguration:
    """Runtime attribution policy defaults."""

    default_confidence_threshold: float
    max_candidate_scope_size: int
    require_attribution_for_identity_context: bool


@dataclass(slots=True, frozen=True)
class VoiceIdentityConfiguration:
    """Authoritative typed runtime configuration for the integration."""

    config_schema_version: int
    service: ServiceConfiguration
    storage: StorageConfiguration
    generation: GenerationConfiguration
    cleanup: CleanupConfiguration
    diagnostics: DiagnosticsConfiguration
    feature_flags: FeatureFlagsConfiguration
    attribution: AttributionConfiguration


class VoiceIdentityConfigurationValidator:
    """Validates and constructs typed configuration state."""

    def validate(self, raw_config: Mapping[str, Any]) -> VoiceIdentityConfiguration:
        """Validate raw merged config and return typed configuration."""
        config_schema_version = self._read_schema_version(raw_config)

        service = self._build_service(self._read_section(raw_config, CONF_SERVICE))
        storage = self._build_storage(self._read_section(raw_config, CONF_STORAGE))
        generation = self._build_generation(self._read_section(raw_config, CONF_GENERATION))
        cleanup = self._build_cleanup(self._read_section(raw_config, CONF_CLEANUP))
        diagnostics = self._build_diagnostics(self._read_section(raw_config, CONF_DIAGNOSTICS))
        feature_flags = self._build_feature_flags(self._read_section(raw_config, CONF_FEATURE_FLAGS))
        attribution = self._build_attribution(self._read_section(raw_config, CONF_ATTRIBUTION))

        if (
            attribution.require_attribution_for_identity_context
            and not feature_flags.enable_runtime_attribution
        ):
            raise VoiceIdentityConfigurationValidationError(
                "Invalid attribution configuration: "
                "require_attribution_for_identity_context requires "
                "feature_flags.enable_runtime_attribution=true."
            )

        return VoiceIdentityConfiguration(
            config_schema_version=config_schema_version,
            service=service,
            storage=storage,
            generation=generation,
            cleanup=cleanup,
            diagnostics=diagnostics,
            feature_flags=feature_flags,
            attribution=attribution,
        )

    def _read_schema_version(self, raw_config: Mapping[str, Any]) -> int:
        value = raw_config.get(CONF_CONFIG_SCHEMA_VERSION, CONFIG_SCHEMA_VERSION_CURRENT)
        if not isinstance(value, int):
            raise VoiceIdentityConfigurationValidationError(
                f"{CONF_CONFIG_SCHEMA_VERSION} must be an integer."
            )

        if value < CONFIG_SCHEMA_VERSION_MINIMUM_SUPPORTED:
            raise VoiceIdentityConfigMigrationRequiredError(
                "Configuration schema version is too old. "
                f"Found {value}, minimum supported is "
                f"{CONFIG_SCHEMA_VERSION_MINIMUM_SUPPORTED}."
            )

        if value > CONFIG_SCHEMA_VERSION_CURRENT:
            raise VoiceIdentityUnsupportedConfigVersionError(
                "Configuration schema version is newer than supported. "
                f"Found {value}, current supported is {CONFIG_SCHEMA_VERSION_CURRENT}."
            )

        return value

    def _build_service(self, section: Mapping[str, Any]) -> ServiceConfiguration:
        enabled = _read_bool(section, CONF_SERVICE_ENABLED, DEFAULT_SERVICE_ENABLED)
        startup_timeout = _read_int(
            section,
            CONF_STARTUP_TIMEOUT_SECONDS,
            DEFAULT_STARTUP_TIMEOUT_SECONDS,
            minimum=1,
            maximum=300,
        )
        max_cached_voiceprints = _read_int(
            section,
            CONF_MAX_CACHED_VOICEPRINTS,
            DEFAULT_MAX_CACHED_VOICEPRINTS,
            minimum=1,
            maximum=100_000,
        )
        return ServiceConfiguration(
            enabled=enabled,
            startup_timeout_seconds=startup_timeout,
            max_cached_voiceprints=max_cached_voiceprints,
        )

    def _build_storage(self, section: Mapping[str, Any]) -> StorageConfiguration:
        provider = _read_str(section, CONF_STORAGE_PROVIDER, DEFAULT_STORAGE_PROVIDER)
        base_path = _read_str(section, CONF_STORAGE_BASE_PATH, DEFAULT_STORAGE_BASE_PATH)
        encryption_required = _read_bool(
            section,
            CONF_STORAGE_ENCRYPTION_REQUIRED,
            DEFAULT_STORAGE_ENCRYPTION_REQUIRED,
        )
        return StorageConfiguration(
            provider=provider,
            base_path=base_path,
            encryption_required=encryption_required,
        )

    def _build_generation(self, section: Mapping[str, Any]) -> GenerationConfiguration:
        model_preference = _read_str(section, CONF_MODEL_PREFERENCE, DEFAULT_MODEL_PREFERENCE)
        min_sample_count = _read_int(
            section,
            CONF_MIN_SAMPLE_COUNT,
            DEFAULT_MIN_SAMPLE_COUNT,
            minimum=1,
            maximum=64,
        )
        max_sample_count = _read_int(
            section,
            CONF_MAX_SAMPLE_COUNT,
            DEFAULT_MAX_SAMPLE_COUNT,
            minimum=1,
            maximum=128,
        )
        if max_sample_count < min_sample_count:
            raise VoiceIdentityConfigurationValidationError(
                "generation.max_sample_count must be greater than or equal to "
                "generation.min_sample_count."
            )

        quality_threshold = _read_float(
            section,
            CONF_QUALITY_THRESHOLD,
            DEFAULT_QUALITY_THRESHOLD,
            minimum=0.0,
            maximum=1.0,
        )

        supported_models_raw = section.get(CONF_SUPPORTED_MODELS, DEFAULT_SUPPORTED_MODELS)
        supported_models = _read_string_tuple(
            supported_models_raw,
            f"{CONF_GENERATION}.{CONF_SUPPORTED_MODELS}",
        )
        if not supported_models:
            raise VoiceIdentityConfigurationValidationError(
                "generation.supported_models must contain at least one model name."
            )

        return GenerationConfiguration(
            model_preference=model_preference,
            min_sample_count=min_sample_count,
            max_sample_count=max_sample_count,
            quality_threshold=quality_threshold,
            supported_models=supported_models,
        )

    def _build_cleanup(self, section: Mapping[str, Any]) -> CleanupConfiguration:
        enabled = _read_bool(section, CONF_CLEANUP_ENABLED, DEFAULT_CLEANUP_ENABLED)
        session_timeout_seconds = _read_int(
            section,
            CONF_SESSION_TIMEOUT_SECONDS,
            DEFAULT_SESSION_TIMEOUT_SECONDS,
            minimum=60,
            maximum=86_400,
        )
        reconcile_on_startup = _read_bool(
            section,
            CONF_RECONCILE_ON_STARTUP,
            DEFAULT_RECONCILE_ON_STARTUP,
        )
        return CleanupConfiguration(
            enabled=enabled,
            session_timeout_seconds=session_timeout_seconds,
            reconcile_on_startup=reconcile_on_startup,
        )

    def _build_diagnostics(self, section: Mapping[str, Any]) -> DiagnosticsConfiguration:
        enabled = _read_bool(section, CONF_DIAGNOSTICS_ENABLED, DEFAULT_DIAGNOSTICS_ENABLED)
        allowlist_only = _read_bool(
            section,
            CONF_DIAGNOSTICS_ALLOWLIST_ONLY,
            DEFAULT_DIAGNOSTICS_ALLOWLIST_ONLY,
        )
        include_runtime_metrics = _read_bool(
            section,
            CONF_INCLUDE_RUNTIME_METRICS,
            DEFAULT_INCLUDE_RUNTIME_METRICS,
        )

        if not allowlist_only:
            raise VoiceIdentityConfigurationValidationError(
                "diagnostics.allowlist_only must remain true for privacy guardrails."
            )

        return DiagnosticsConfiguration(
            enabled=enabled,
            allowlist_only=allowlist_only,
            include_runtime_metrics=include_runtime_metrics,
        )

    def _build_feature_flags(self, section: Mapping[str, Any]) -> FeatureFlagsConfiguration:
        return FeatureFlagsConfiguration(
            enable_runtime_attribution=_read_bool(
                section,
                CONF_ENABLE_RUNTIME_ATTRIBUTION,
                DEFAULT_ENABLE_RUNTIME_ATTRIBUTION,
            ),
            enable_repairs=_read_bool(section, CONF_ENABLE_REPAIRS, DEFAULT_ENABLE_REPAIRS),
            enable_experimental_models=_read_bool(
                section,
                CONF_ENABLE_EXPERIMENTAL_MODELS,
                DEFAULT_ENABLE_EXPERIMENTAL_MODELS,
            ),
        )

    def _build_attribution(self, section: Mapping[str, Any]) -> AttributionConfiguration:
        return AttributionConfiguration(
            default_confidence_threshold=_read_float(
                section,
                CONF_DEFAULT_CONFIDENCE_THRESHOLD,
                DEFAULT_DEFAULT_CONFIDENCE_THRESHOLD,
                minimum=0.0,
                maximum=1.0,
            ),
            max_candidate_scope_size=_read_int(
                section,
                CONF_MAX_CANDIDATE_SCOPE_SIZE,
                DEFAULT_MAX_CANDIDATE_SCOPE_SIZE,
                minimum=1,
                maximum=1000,
            ),
            require_attribution_for_identity_context=_read_bool(
                section,
                CONF_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
                DEFAULT_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
            ),
        )

    def _read_section(self, raw_config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        section = raw_config.get(key, {})
        if not isinstance(section, Mapping):
            raise VoiceIdentityConfigurationValidationError(
                f"{key} must be a mapping/object."
            )
        return section


class VoiceIdentityConfigurationManager:
    """Authoritative runtime configuration provider for Voice Identity."""

    def __init__(
        self,
        validator: VoiceIdentityConfigurationValidator | None = None,
    ) -> None:
        self._validator = validator or VoiceIdentityConfigurationValidator()
        self._config: VoiceIdentityConfiguration | None = None
        self._entry_id: str | None = None

    def load_from_entry(self, entry: SupportsConfigEntry) -> VoiceIdentityConfiguration:
        """Load, validate, and cache configuration from a config entry."""
        merged = _deep_merge_dicts(entry.data, entry.options)
        config = self._validator.validate(merged)

        self._entry_id = entry.entry_id
        self._config = config
        return config

    def reload_from_entry(self, entry: SupportsConfigEntry) -> VoiceIdentityConfiguration:
        """Reload configuration from a config entry and replace cached state."""
        return self.load_from_entry(entry)

    def clear(self) -> None:
        """Reset cached configuration state."""
        self._entry_id = None
        self._config = None

    @property
    def config(self) -> VoiceIdentityConfiguration:
        """Return the current typed configuration.

        Raises when config has not been loaded yet.
        """
        if self._config is None:
            raise VoiceIdentityConfigurationNotLoadedError(
                "Configuration has not been loaded yet. "
                "Call load_from_entry before reading configuration."
            )
        return self._config

    @property
    def entry_id(self) -> str | None:
        """Return the config entry id associated with cached configuration."""
        return self._entry_id


def _deep_merge_dicts(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep merge two mapping values where override takes precedence."""
    merged: dict[str, Any] = dict(base)

    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge_dicts(existing, value)
            continue
        merged[key] = value

    return merged


def _read_bool(section: Mapping[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise VoiceIdentityConfigurationValidationError(f"{key} must be a boolean.")
    return value


def _read_int(
    section: Mapping[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise VoiceIdentityConfigurationValidationError(f"{key} must be an integer.")
    if value < minimum or value > maximum:
        raise VoiceIdentityConfigurationValidationError(
            f"{key} must be between {minimum} and {maximum}."
        )
    return value


def _read_float(
    section: Mapping[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = section.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VoiceIdentityConfigurationValidationError(f"{key} must be numeric.")

    numeric_value = float(value)
    if numeric_value < minimum or numeric_value > maximum:
        raise VoiceIdentityConfigurationValidationError(
            f"{key} must be between {minimum} and {maximum}."
        )
    return numeric_value


def _read_str(section: Mapping[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise VoiceIdentityConfigurationValidationError(f"{key} must be a string.")

    stripped = value.strip()
    if not stripped:
        raise VoiceIdentityConfigurationValidationError(f"{key} must not be empty.")
    return stripped


def _read_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise VoiceIdentityConfigurationValidationError(
            f"{field_name} must be a list/tuple of strings."
        )

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise VoiceIdentityConfigurationValidationError(
                f"{field_name} entries must be strings."
            )
        stripped = item.strip()
        if not stripped:
            raise VoiceIdentityConfigurationValidationError(
                f"{field_name} entries must not be empty strings."
            )
        normalized.append(stripped)

    return tuple(normalized)
