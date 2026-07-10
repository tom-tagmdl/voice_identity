from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custom_components.voice_identity.config_flow import (
    _form_defaults,
    _is_payload_valid,
    _normalize_form_data,
)
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.const import (
    CONF_CONFIG_SCHEMA_VERSION,
    CONF_GENERATION,
    CONF_MAX_SAMPLE_COUNT,
    CONF_MIN_SAMPLE_COUNT,
    CONF_SUPPORTED_MODELS,
    CONFIG_SCHEMA_VERSION_CURRENT,
)


@dataclass(slots=True)
class FakeConfigEntry:
    entry_id: str = "entry-1"
    data: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


def test_form_defaults_include_expected_flat_fields() -> None:
    defaults = _form_defaults()

    assert defaults["service_enabled"] is True
    assert defaults["generation_supported_models"] == "ecapa_v1"
    assert defaults["attribution_require_attribution_for_identity_context"] is False


def test_form_defaults_merge_existing_entry_values() -> None:
    entry = FakeConfigEntry(
        data={
            CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT,
            CONF_GENERATION: {
                CONF_MIN_SAMPLE_COUNT: 4,
                CONF_MAX_SAMPLE_COUNT: 8,
                CONF_SUPPORTED_MODELS: ("ecapa_v1", "ecapa_v2"),
            },
        },
        options={
            CONF_GENERATION: {
                CONF_MIN_SAMPLE_COUNT: 6,
            }
        },
    )

    defaults = _form_defaults(entry)

    assert defaults["generation_min_sample_count"] == 6
    assert defaults["generation_max_sample_count"] == 8
    assert defaults["generation_supported_models"] == "ecapa_v1, ecapa_v2"


def test_normalize_form_data_converts_flat_input_to_nested_sections() -> None:
    payload = _normalize_form_data(
        {
            "service_enabled": True,
            "service_startup_timeout_seconds": 45,
            "service_max_cached_voiceprints": 1234,
            "storage_provider": "local_filesystem",
            "storage_base_path": "voice_identity",
            "storage_encryption_required": True,
            "generation_model_preference": "ecapa_v1",
            "generation_min_sample_count": 4,
            "generation_max_sample_count": 8,
            "generation_quality_threshold": 0.8,
            "generation_supported_models": "ecapa_v1, ecapa_v2",
            "cleanup_enabled": True,
            "cleanup_session_timeout_seconds": 900,
            "cleanup_reconcile_on_startup": True,
            "diagnostics_enabled": True,
            "diagnostics_allowlist_only": True,
            "diagnostics_include_runtime_metrics": False,
            "feature_flags_enable_runtime_attribution": False,
            "feature_flags_enable_repairs": True,
            "feature_flags_enable_experimental_models": False,
            "attribution_default_confidence_threshold": 0.7,
            "attribution_max_candidate_scope_size": 25,
            "attribution_require_attribution_for_identity_context": False,
        }
    )

    assert payload["generation"][CONF_MIN_SAMPLE_COUNT] == 4
    assert payload["generation"][CONF_MAX_SAMPLE_COUNT] == 8
    assert payload["generation"][CONF_SUPPORTED_MODELS] == ("ecapa_v1", "ecapa_v2")
    assert payload["diagnostics"]["allowlist_only"] is True
    assert payload["feature_flags"]["enable_repairs"] is True


def test_normalized_payload_loads_into_configuration_manager() -> None:
    manager = VoiceIdentityConfigurationManager()
    payload = _normalize_form_data(
        {
            "service_enabled": True,
            "service_startup_timeout_seconds": 30,
            "service_max_cached_voiceprints": 2500,
            "storage_provider": "local_filesystem",
            "storage_base_path": "voice_identity",
            "storage_encryption_required": True,
            "generation_model_preference": "ecapa_v1",
            "generation_min_sample_count": 6,
            "generation_max_sample_count": 12,
            "generation_quality_threshold": 0.75,
            "generation_supported_models": "ecapa_v1",
            "cleanup_enabled": True,
            "cleanup_session_timeout_seconds": 900,
            "cleanup_reconcile_on_startup": True,
            "diagnostics_enabled": True,
            "diagnostics_allowlist_only": True,
            "diagnostics_include_runtime_metrics": True,
            "feature_flags_enable_runtime_attribution": False,
            "feature_flags_enable_repairs": True,
            "feature_flags_enable_experimental_models": False,
            "attribution_default_confidence_threshold": 0.7,
            "attribution_max_candidate_scope_size": 25,
            "attribution_require_attribution_for_identity_context": False,
        }
    )

    config = manager.load_from_entry(
        FakeConfigEntry(
            data={CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT, **payload},
        )
    )

    assert config.generation.min_sample_count == 6
    assert config.generation.max_sample_count == 12
    assert config.generation.supported_models == ("ecapa_v1",)


def test_reconfigure_payload_validation_uses_existing_entry_data() -> None:
    existing_data = {
        CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT,
        CONF_GENERATION: {
            CONF_MIN_SAMPLE_COUNT: 6,
            CONF_MAX_SAMPLE_COUNT: 12,
            CONF_SUPPORTED_MODELS: ("ecapa_v1",),
        },
    }
    payload = _normalize_form_data(
        {
            "service_enabled": True,
            "service_startup_timeout_seconds": 30,
            "service_max_cached_voiceprints": 2500,
            "storage_provider": "local_filesystem",
            "storage_base_path": "voice_identity",
            "storage_encryption_required": True,
            "generation_model_preference": "ecapa_v1",
            "generation_min_sample_count": 6,
            "generation_max_sample_count": 12,
            "generation_quality_threshold": 0.75,
            "generation_supported_models": "ecapa_v1",
            "cleanup_enabled": True,
            "cleanup_session_timeout_seconds": 900,
            "cleanup_reconcile_on_startup": True,
            "diagnostics_enabled": True,
            "diagnostics_allowlist_only": True,
            "diagnostics_include_runtime_metrics": True,
            "feature_flags_enable_runtime_attribution": False,
            "feature_flags_enable_repairs": True,
            "feature_flags_enable_experimental_models": False,
            "attribution_default_confidence_threshold": 0.7,
            "attribution_max_candidate_scope_size": 25,
            "attribution_require_attribution_for_identity_context": False,
        }
    )

    assert _is_payload_valid(payload, existing_data=existing_data) is True
