from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from custom_components.voice_identity.configuration import (
    VoiceIdentityConfigMigrationRequiredError,
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigurationNotLoadedError,
    VoiceIdentityConfigurationValidationError,
    VoiceIdentityUnsupportedConfigVersionError,
)
from custom_components.voice_identity.const import (
    CONFIG_SCHEMA_VERSION_CURRENT,
    CONF_ATTRIBUTION,
    CONF_CONFIG_SCHEMA_VERSION,
    CONF_DIAGNOSTICS,
    CONF_DIAGNOSTICS_ALLOWLIST_ONLY,
    CONF_FEATURE_FLAGS,
    CONF_GENERATION,
    CONF_MAX_SAMPLE_COUNT,
    CONF_MIN_SAMPLE_COUNT,
    CONF_MODEL_PREFERENCE,
    CONF_QUALITY_THRESHOLD,
    CONF_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT,
    CONF_SUPPORTED_MODELS,
    DEFAULT_DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DIAGNOSTICS_ALLOWLIST_ONLY,
    DEFAULT_MAX_SAMPLE_COUNT,
    DEFAULT_MIN_SAMPLE_COUNT,
    DEFAULT_MODEL_PREFERENCE,
)


@dataclass(slots=True)
class FakeConfigEntry:
    entry_id: str = "entry-1"
    data: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


def test_load_defaults_when_entry_has_no_data() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry()

    config = manager.load_from_entry(entry)

    assert config.config_schema_version == CONFIG_SCHEMA_VERSION_CURRENT
    assert config.generation.model_preference == DEFAULT_MODEL_PREFERENCE
    assert config.generation.min_sample_count == DEFAULT_MIN_SAMPLE_COUNT
    assert config.generation.max_sample_count == DEFAULT_MAX_SAMPLE_COUNT
    assert config.attribution.default_confidence_threshold == DEFAULT_DEFAULT_CONFIDENCE_THRESHOLD
    assert config.diagnostics.allowlist_only is DEFAULT_DIAGNOSTICS_ALLOWLIST_ONLY


def test_load_valid_configuration_and_option_overrides() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT,
            CONF_GENERATION: {
                CONF_MODEL_PREFERENCE: "ecapa_v1",
                CONF_MIN_SAMPLE_COUNT: 4,
                CONF_MAX_SAMPLE_COUNT: 8,
                CONF_QUALITY_THRESHOLD: 0.6,
                CONF_SUPPORTED_MODELS: ["ecapa_v1", "ecapa_v2"],
            },
        },
        options={
            CONF_GENERATION: {
                CONF_MAX_SAMPLE_COUNT: 10,
            },
        },
    )

    config = manager.load_from_entry(entry)

    assert config.generation.min_sample_count == 4
    assert config.generation.max_sample_count == 10
    assert config.generation.quality_threshold == 0.6
    assert config.generation.supported_models == ("ecapa_v1", "ecapa_v2")


def test_invalid_configuration_rejects_out_of_range_quality_threshold() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_GENERATION: {
                CONF_QUALITY_THRESHOLD: 1.2,
            },
        }
    )

    with pytest.raises(VoiceIdentityConfigurationValidationError):
        manager.load_from_entry(entry)


def test_invalid_configuration_rejects_invalid_diagnostics_guardrail() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_DIAGNOSTICS: {
                CONF_DIAGNOSTICS_ALLOWLIST_ONLY: False,
            }
        }
    )

    with pytest.raises(VoiceIdentityConfigurationValidationError):
        manager.load_from_entry(entry)


def test_invalid_configuration_rejects_inconsistent_attribution_flags() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_FEATURE_FLAGS: {
                "enable_runtime_attribution": False,
            },
            CONF_ATTRIBUTION: {
                CONF_REQUIRE_ATTRIBUTION_FOR_IDENTITY_CONTEXT: True,
            },
        }
    )

    with pytest.raises(VoiceIdentityConfigurationValidationError):
        manager.load_from_entry(entry)


def test_version_handling_rejects_unsupported_future_schema() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT + 1,
        }
    )

    with pytest.raises(VoiceIdentityUnsupportedConfigVersionError):
        manager.load_from_entry(entry)


def test_version_handling_requires_migration_for_too_old_schema() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_CONFIG_SCHEMA_VERSION: 0,
        }
    )

    with pytest.raises(VoiceIdentityConfigMigrationRequiredError):
        manager.load_from_entry(entry)


def test_reload_updates_cached_configuration() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(
        data={
            CONF_GENERATION: {
                CONF_MIN_SAMPLE_COUNT: 5,
                CONF_MAX_SAMPLE_COUNT: 10,
            }
        }
    )

    first = manager.load_from_entry(entry)
    assert first.generation.min_sample_count == 5

    entry.options = {
        CONF_GENERATION: {
            CONF_MIN_SAMPLE_COUNT: 7,
            CONF_MAX_SAMPLE_COUNT: 11,
        }
    }

    reloaded = manager.reload_from_entry(entry)

    assert reloaded.generation.min_sample_count == 7
    assert reloaded.generation.max_sample_count == 11
    assert manager.config == reloaded


def test_accessing_config_before_load_raises_error() -> None:
    manager = VoiceIdentityConfigurationManager()

    with pytest.raises(VoiceIdentityConfigurationNotLoadedError):
        _ = manager.config


def test_clear_resets_cached_state() -> None:
    manager = VoiceIdentityConfigurationManager()
    entry = FakeConfigEntry(data={CONF_CONFIG_SCHEMA_VERSION: CONFIG_SCHEMA_VERSION_CURRENT})

    manager.load_from_entry(entry)
    manager.clear()

    assert manager.entry_id is None
    with pytest.raises(VoiceIdentityConfigurationNotLoadedError):
        _ = manager.config