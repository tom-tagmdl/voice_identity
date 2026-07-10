"""Config flow for Voice Identity integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .configuration import VoiceIdentityConfigurationValidationError, VoiceIdentityConfigurationValidator
from .const import (
    CONFIG_SCHEMA_VERSION_CURRENT,
    CONF_CONFIG_SCHEMA_VERSION,
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
    DOMAIN,
)


def _form_defaults(config_entry: config_entries.ConfigEntry | None = None) -> dict[str, object]:
    """Return defaults for the flattened form fields."""
    defaults = {
        "service_enabled": DEFAULT_SERVICE_ENABLED,
        "service_startup_timeout_seconds": DEFAULT_STARTUP_TIMEOUT_SECONDS,
        "service_max_cached_voiceprints": DEFAULT_MAX_CACHED_VOICEPRINTS,
        "storage_provider": DEFAULT_STORAGE_PROVIDER,
        "storage_base_path": DEFAULT_STORAGE_BASE_PATH,
        "storage_encryption_required": DEFAULT_STORAGE_ENCRYPTION_REQUIRED,
        "generation_model_preference": DEFAULT_MODEL_PREFERENCE,
        "generation_min_sample_count": DEFAULT_MIN_SAMPLE_COUNT,
        "generation_max_sample_count": DEFAULT_MAX_SAMPLE_COUNT,
        "generation_quality_threshold": DEFAULT_QUALITY_THRESHOLD,
        "generation_supported_models": ", ".join(DEFAULT_SUPPORTED_MODELS),
        "cleanup_enabled": DEFAULT_CLEANUP_ENABLED,
        "cleanup_session_timeout_seconds": DEFAULT_SESSION_TIMEOUT_SECONDS,
        "cleanup_reconcile_on_startup": DEFAULT_RECONCILE_ON_STARTUP,
        "diagnostics_enabled": DEFAULT_DIAGNOSTICS_ENABLED,
        "diagnostics_allowlist_only": DEFAULT_DIAGNOSTICS_ALLOWLIST_ONLY,
        "diagnostics_include_runtime_metrics": DEFAULT_INCLUDE_RUNTIME_METRICS,
        "feature_flags_enable_runtime_attribution": DEFAULT_ENABLE_RUNTIME_ATTRIBUTION,
        "feature_flags_enable_repairs": DEFAULT_ENABLE_REPAIRS,
        "feature_flags_enable_experimental_models": DEFAULT_ENABLE_EXPERIMENTAL_MODELS,
        "attribution_default_confidence_threshold": DEFAULT_DEFAULT_CONFIDENCE_THRESHOLD,
        "attribution_max_candidate_scope_size": DEFAULT_MAX_CANDIDATE_SCOPE_SIZE,
        "attribution_require_attribution_for_identity_context": DEFAULT_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
    }

    if config_entry is None:
        return defaults

    merged = {**config_entry.data, **config_entry.options}
    for field_name, (section, section_key) in {
        "service_enabled": ("service", "enabled"),
        "service_startup_timeout_seconds": ("service", "startup_timeout_seconds"),
        "service_max_cached_voiceprints": ("service", "max_cached_voiceprints"),
        "storage_provider": ("storage", "provider"),
        "storage_base_path": ("storage", "base_path"),
        "storage_encryption_required": ("storage", "encryption_required"),
        "generation_model_preference": ("generation", "model_preference"),
        "generation_min_sample_count": ("generation", "min_sample_count"),
        "generation_max_sample_count": ("generation", "max_sample_count"),
        "generation_quality_threshold": ("generation", "quality_threshold"),
        "generation_supported_models": ("generation", "supported_models"),
        "cleanup_enabled": ("cleanup", "enabled"),
        "cleanup_session_timeout_seconds": ("cleanup", "session_timeout_seconds"),
        "cleanup_reconcile_on_startup": ("cleanup", "reconcile_on_startup"),
        "diagnostics_enabled": ("diagnostics", "enabled"),
        "diagnostics_allowlist_only": ("diagnostics", "allowlist_only"),
        "diagnostics_include_runtime_metrics": ("diagnostics", "include_runtime_metrics"),
        "feature_flags_enable_runtime_attribution": ("feature_flags", "enable_runtime_attribution"),
        "feature_flags_enable_repairs": ("feature_flags", "enable_repairs"),
        "feature_flags_enable_experimental_models": ("feature_flags", "enable_experimental_models"),
        "attribution_default_confidence_threshold": ("attribution", "default_confidence_threshold"),
        "attribution_max_candidate_scope_size": ("attribution", "max_candidate_scope_size"),
        "attribution_require_attribution_for_identity_context": ("attribution", "require_attribution_for_identity_context"),
    }.items():
        section_values = merged.get(section)
        if isinstance(section_values, dict) and section_key in section_values:
            value = section_values[section_key]
            if field_name == "generation_supported_models" and isinstance(value, (tuple, list)):
                defaults[field_name] = ", ".join(value)
            else:
                defaults[field_name] = value

    return defaults


def _build_form_schema(config_entry: config_entries.ConfigEntry | None = None) -> vol.Schema:
    """Build the flat form schema used by setup and options flows."""
    defaults = _form_defaults(config_entry)
    return vol.Schema(
        {
            vol.Required("service_enabled", default=defaults["service_enabled"]): cv.boolean,
            vol.Required(
                "service_startup_timeout_seconds",
                default=defaults["service_startup_timeout_seconds"],
            ): cv.positive_int,
            vol.Required(
                "service_max_cached_voiceprints",
                default=defaults["service_max_cached_voiceprints"],
            ): cv.positive_int,
            vol.Required("storage_provider", default=defaults["storage_provider"]): cv.string,
            vol.Required("storage_base_path", default=defaults["storage_base_path"]): cv.string,
            vol.Required(
                "storage_encryption_required",
                default=defaults["storage_encryption_required"],
            ): cv.boolean,
            vol.Required(
                "generation_model_preference",
                default=defaults["generation_model_preference"],
            ): cv.string,
            vol.Required(
                "generation_min_sample_count",
                default=defaults["generation_min_sample_count"],
            ): cv.positive_int,
            vol.Required(
                "generation_max_sample_count",
                default=defaults["generation_max_sample_count"],
            ): cv.positive_int,
            vol.Required(
                "generation_quality_threshold",
                default=defaults["generation_quality_threshold"],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Required(
                "generation_supported_models",
                default=defaults["generation_supported_models"],
            ): cv.string,
            vol.Required("cleanup_enabled", default=defaults["cleanup_enabled"]): cv.boolean,
            vol.Required(
                "cleanup_session_timeout_seconds",
                default=defaults["cleanup_session_timeout_seconds"],
            ): cv.positive_int,
            vol.Required(
                "cleanup_reconcile_on_startup",
                default=defaults["cleanup_reconcile_on_startup"],
            ): cv.boolean,
            vol.Required("diagnostics_enabled", default=defaults["diagnostics_enabled"]): cv.boolean,
            vol.Required(
                "diagnostics_allowlist_only",
                default=defaults["diagnostics_allowlist_only"],
            ): cv.boolean,
            vol.Required(
                "diagnostics_include_runtime_metrics",
                default=defaults["diagnostics_include_runtime_metrics"],
            ): cv.boolean,
            vol.Required(
                "feature_flags_enable_runtime_attribution",
                default=defaults["feature_flags_enable_runtime_attribution"],
            ): cv.boolean,
            vol.Required(
                "feature_flags_enable_repairs",
                default=defaults["feature_flags_enable_repairs"],
            ): cv.boolean,
            vol.Required(
                "feature_flags_enable_experimental_models",
                default=defaults["feature_flags_enable_experimental_models"],
            ): cv.boolean,
            vol.Required(
                "attribution_default_confidence_threshold",
                default=defaults["attribution_default_confidence_threshold"],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Required(
                "attribution_max_candidate_scope_size",
                default=defaults["attribution_max_candidate_scope_size"],
            ): cv.positive_int,
            vol.Required(
                "attribution_require_attribution_for_identity_context",
                default=defaults["attribution_require_attribution_for_identity_context"],
            ): cv.boolean,
        }
    )


def _normalize_form_data(user_input: dict[str, object]) -> dict[str, dict[str, object]]:
    """Convert flattened form input into config-entry section payloads."""
    supported_models = user_input["generation_supported_models"]
    if isinstance(supported_models, str):
        supported_models_value = tuple(
            item.strip() for item in supported_models.split(",") if item.strip()
        )
    else:
        supported_models_value = tuple(supported_models)

    return {
        "service": {
            "enabled": user_input["service_enabled"],
            "startup_timeout_seconds": user_input["service_startup_timeout_seconds"],
            "max_cached_voiceprints": user_input["service_max_cached_voiceprints"],
        },
        "storage": {
            "provider": user_input["storage_provider"],
            "base_path": user_input["storage_base_path"],
            "encryption_required": user_input["storage_encryption_required"],
        },
        "generation": {
            "model_preference": user_input["generation_model_preference"],
            "min_sample_count": user_input["generation_min_sample_count"],
            "max_sample_count": user_input["generation_max_sample_count"],
            "quality_threshold": user_input["generation_quality_threshold"],
            "supported_models": supported_models_value,
        },
        "cleanup": {
            "enabled": user_input["cleanup_enabled"],
            "session_timeout_seconds": user_input["cleanup_session_timeout_seconds"],
            "reconcile_on_startup": user_input["cleanup_reconcile_on_startup"],
        },
        "diagnostics": {
            "enabled": user_input["diagnostics_enabled"],
            "allowlist_only": user_input["diagnostics_allowlist_only"],
            "include_runtime_metrics": user_input["diagnostics_include_runtime_metrics"],
        },
        "feature_flags": {
            "enable_runtime_attribution": user_input["feature_flags_enable_runtime_attribution"],
            "enable_repairs": user_input["feature_flags_enable_repairs"],
            "enable_experimental_models": user_input["feature_flags_enable_experimental_models"],
        },
        "attribution": {
            "default_confidence_threshold": user_input["attribution_default_confidence_threshold"],
            "max_candidate_scope_size": user_input["attribution_max_candidate_scope_size"],
            "require_attribution_for_identity_context": user_input["attribution_require_attribution_for_identity_context"],
        },
    }


def _is_payload_valid(
    payload: dict[str, dict[str, object]],
    *,
    existing_data: dict[str, object] | None = None,
) -> bool:
    """Return whether a normalized payload is valid against existing entry data."""
    merged = {CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT, **(existing_data or {}), **payload}

    try:
        VoiceIdentityConfigurationValidator().validate(merged)
    except VoiceIdentityConfigurationValidationError:
        return False

    return True


class VoiceIdentityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Identity."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create an initial config entry with runtime defaults or user choices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            options = _normalize_form_data(user_input)
            if not _is_payload_valid(options):
                errors["base"] = "invalid_options"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Voice Identity",
                    data={CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT, **options},
                )

        return self.async_show_form(step_id="user", data_schema=_build_form_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing Voice Identity entry."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            options = _normalize_form_data(user_input)
            if not _is_payload_valid(options, existing_data=reconfigure_entry.data):
                errors["base"] = "invalid_options"
            else:
                await self.async_set_unique_id(reconfigure_entry.unique_id or DOMAIN)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT, **options},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_form_schema(reconfigure_entry),
            errors=errors,
            description_placeholders={"name": reconfigure_entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VoiceIdentityOptionsFlow(config_entry)


class VoiceIdentityOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Voice Identity."""

    def __init__(self, config_entry):
        self._config_entry = config_entry
        self._validator = VoiceIdentityConfigurationValidator()

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            options = _normalize_form_data(user_input)
            merged = {**self._config_entry.data, **options}

            try:
                self._validator.validate(merged)
            except VoiceIdentityConfigurationValidationError:
                errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_form_schema(self._config_entry),
            errors=errors,
        )
