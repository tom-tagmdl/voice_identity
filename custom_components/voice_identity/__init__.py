"""Voice Identity Home Assistant integration scaffold."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .capability_registry import VoiceIdentityCapabilityRegistry
from .configuration import (
    VoiceIdentityConfigurationError,
    VoiceIdentityConfigurationManager,
)
from .health_state import VoiceIdentityHealthStateEngine
from .health_telemetry import VoiceIdentityHealthTelemetryProvider
from .artifact_persistence import ArtifactPersistenceEngine
from .artifact_integrity import ArtifactIntegrityValidator
from .generation_orchestrator import (
    GenerationOrchestrator,
)
from .generate_voiceprint_operation import GenerateVoiceprintOperation
from .voiceprint_status_metadata_operation import GetVoiceprintStatusOperation
from .capability_discovery_operation import GetCapabilitiesOperation
from .concierge_discovery_integration import ConciergeDiscoveryIntegration
from .concierge_voiceprofile_metadata_integration import ConciergeVoiceProfileMetadataIntegration
from .delete_supersede_voiceprint_operation import DeleteSupersedeVoiceprintOperation
from .model_execution import ModelExecutionProviderRuntime
from .quality_scoring import QualityScoringEngineProvider
from .repair_registry import VoiceIdentityRepairRegistry
from .repair_resolver import VoiceIdentityRepairResolver
from .attribution_service import SpeakerAttributionFoundation
from .attribution_context_store import InMemoryAttributionContextStore
from .identity_context import IdentityContextGenerator
from .sample_validation import SampleValidationPipelineProvider
from .voiceprint_revision import VoiceprintRevisionManager
from .storage_provider import LocalFileVoiceprintStorageProvider
from .services import async_register_services, async_unregister_services
from .voiceprint_lifecycle import VoiceprintLifecycleManager
from .voiceprint_registry import VoiceprintRegistry
from .const import (
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_HEALTH_ENGINE,
    DATA_ARTIFACT_PERSISTENCE_ENGINE,
    DATA_ARTIFACT_INTEGRITY_VALIDATOR,
    DATA_SAMPLE_VALIDATION_PIPELINE,
    DATA_QUALITY_SCORING_ENGINE,
    DATA_MODEL_EXECUTION_PROVIDER,
    DATA_GENERATION_ORCHESTRATOR,
    DATA_GENERATE_VOICEPRINT_OPERATION,
    DATA_GET_VOICEPRINT_STATUS_OPERATION,
    DATA_GET_CAPABILITIES_OPERATION,
    DATA_CONCIERGE_DISCOVERY_INTEGRATION,
    DATA_CONCIERGE_VOICEPROFILE_METADATA_INTEGRATION,
    DATA_DELETE_SUPERSEDE_VOICEPRINT_OPERATION,
    DATA_HEALTH_TELEMETRY_PROVIDER,
    DATA_ATTRIBUTION_FOUNDATION,
    DATA_ATTRIBUTION_CONTEXT_STORE,
    DATA_IDENTITY_CONTEXT_GENERATOR,
    DATA_REPAIR_REGISTRY,
    DATA_REPAIR_RESOLVER,
    DATA_MESSAGE,
    DATA_STORAGE_PROVIDER,
    DATA_STATUS,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REVISION_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DOMAIN,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Voice Identity from YAML (not used)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Identity from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    config_manager = VoiceIdentityConfigurationManager()

    try:
        config_manager.load_from_entry(entry)
    except VoiceIdentityConfigurationError as err:
        raise ConfigEntryError(f"Voice Identity configuration is invalid: {err}") from err

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    capability_registry = VoiceIdentityCapabilityRegistry.from_configuration_manager(config_manager)

    storage_provider = LocalFileVoiceprintStorageProvider.from_configuration_manager(
        config_manager=config_manager,
        ha_config_dir=Path(hass.config.path()),
    )
    storage_health = await storage_provider.validate_availability()
    voiceprint_registry = await VoiceprintRegistry.create(
        hass=hass,
        storage_provider=storage_provider,
    )
    registry_health = await voiceprint_registry.validate_health()
    lifecycle_manager = VoiceprintLifecycleManager.create(registry=voiceprint_registry)
    lifecycle_health = await lifecycle_manager.validate_health()
    revision_manager = VoiceprintRevisionManager.create(
        registry=voiceprint_registry,
        lifecycle_manager=lifecycle_manager,
    )
    revision_health = await revision_manager.validate_health()
    persistence_engine = ArtifactPersistenceEngine.create(
        storage_provider=storage_provider,
        registry=voiceprint_registry,
        lifecycle_manager=lifecycle_manager,
        revision_manager=revision_manager,
    )
    persistence_health = await persistence_engine.validate_health()
    integrity_validator = ArtifactIntegrityValidator.create(
        storage_provider=storage_provider,
        registry=voiceprint_registry,
        revision_manager=revision_manager,
    )
    integrity_health = await integrity_validator.validate_health()
    sample_validation_pipeline = SampleValidationPipelineProvider.create(
        config_manager=config_manager,
    )
    sample_validation_health = await sample_validation_pipeline.validate_health()
    quality_scoring_engine = QualityScoringEngineProvider.create(
        config_manager=config_manager,
    )
    quality_scoring_health = await quality_scoring_engine.validate_health()
    model_execution_provider = ModelExecutionProviderRuntime.create(
        config_manager=config_manager,
    )
    model_execution_health = await model_execution_provider.validate_health()
    generation_orchestrator = GenerationOrchestrator.create(
        config_manager=config_manager,
        validation_pipeline=sample_validation_pipeline,
        quality_engine=quality_scoring_engine,
        model_provider=model_execution_provider,
        persistence_engine=persistence_engine,
        integrity_validator=integrity_validator,
    )
    generation_health = await generation_orchestrator.validate_health()
    generate_voiceprint_operation = GenerateVoiceprintOperation.create(
        orchestrator=generation_orchestrator,
    )
    generate_voiceprint_health = await generate_voiceprint_operation.validate_health()
    get_voiceprint_status_operation = GetVoiceprintStatusOperation.create(
        registry=voiceprint_registry,
        lifecycle_manager=lifecycle_manager,
        revision_manager=revision_manager,
    )
    get_voiceprint_status_health = await get_voiceprint_status_operation.validate_health()
    get_capabilities_operation = GetCapabilitiesOperation.create(
        capability_registry=capability_registry,
    )
    get_capabilities_health = await get_capabilities_operation.validate_health()
    concierge_discovery_integration = ConciergeDiscoveryIntegration.create(
        capabilities_operation=get_capabilities_operation,
    )
    concierge_discovery_health = await concierge_discovery_integration.validate_health()
    concierge_voiceprofile_metadata_integration = ConciergeVoiceProfileMetadataIntegration.create(
        status_operation=get_voiceprint_status_operation,
        discovery_integration=concierge_discovery_integration,
    )
    concierge_voiceprofile_metadata_health = await concierge_voiceprofile_metadata_integration.validate_health()
    delete_supersede_voiceprint_operation = DeleteSupersedeVoiceprintOperation.create(
        registry=voiceprint_registry,
        lifecycle_manager=lifecycle_manager,
        revision_manager=revision_manager,
    )
    delete_supersede_health = await delete_supersede_voiceprint_operation.validate_health()
    health_telemetry_provider = VoiceIdentityHealthTelemetryProvider()
    attribution_foundation = SpeakerAttributionFoundation()
    attribution_context_store = InMemoryAttributionContextStore()
    identity_context_generator = IdentityContextGenerator()
    repair_registry = VoiceIdentityRepairRegistry.with_defaults()
    repair_resolver = VoiceIdentityRepairResolver(registry=repair_registry)

    health_engine = VoiceIdentityHealthStateEngine.from_foundation(
        config_manager=config_manager,
        capability_registry=capability_registry,
        runtime_loaded=True,
    )
    health_engine.set_component(
        component="storage_provider",
        required=True,
        state=storage_health.state,
        reason_codes=storage_health.reason_codes,
        details=storage_health.details,
    )
    health_engine.set_component(
        component="voiceprint_registry",
        required=True,
        state=registry_health.state,
        reason_codes=registry_health.reason_codes,
        details=registry_health.details,
    )
    health_engine.set_component(
        component="voiceprint_lifecycle_manager",
        required=True,
        state=lifecycle_health.state,
        reason_codes=lifecycle_health.reason_codes,
        details=lifecycle_health.details,
    )
    health_engine.set_component(
        component="voiceprint_revision_manager",
        required=True,
        state=revision_health.state,
        reason_codes=revision_health.reason_codes,
        details=revision_health.details,
    )
    health_engine.set_component(
        component="artifact_persistence_engine",
        required=True,
        state=persistence_health.state,
        reason_codes=persistence_health.reason_codes,
        details=persistence_health.details,
    )
    health_engine.set_component(
        component="artifact_integrity_validator",
        required=True,
        state=integrity_health.state,
        reason_codes=integrity_health.reason_codes,
        details=integrity_health.details,
    )
    health_engine.set_component(
        component="sample_validation_pipeline",
        required=True,
        state=sample_validation_health.state,
        reason_codes=sample_validation_health.reason_codes,
        details=sample_validation_health.details,
    )
    health_engine.set_component(
        component="quality_scoring_engine",
        required=True,
        state=quality_scoring_health.state,
        reason_codes=quality_scoring_health.reason_codes,
        details=quality_scoring_health.details,
    )
    health_engine.set_component(
        component="model_execution_provider",
        required=True,
        state=model_execution_health.state,
        reason_codes=model_execution_health.reason_codes,
        details=model_execution_health.details,
    )
    health_engine.set_component(
        component="generation_orchestrator",
        required=True,
        state=generation_health.state,
        reason_codes=generation_health.reason_codes,
        details=generation_health.details,
    )
    health_engine.set_component(
        component="generate_voiceprint_operation",
        required=True,
        state=generate_voiceprint_health.state,
        reason_codes=generate_voiceprint_health.reason_codes,
        details=generate_voiceprint_health.details,
    )
    health_engine.set_component(
        component="get_voiceprint_status_operation",
        required=True,
        state=get_voiceprint_status_health.state,
        reason_codes=get_voiceprint_status_health.reason_codes,
        details=get_voiceprint_status_health.details,
    )
    health_engine.set_component(
        component="get_capabilities_operation",
        required=True,
        state=get_capabilities_health.state,
        reason_codes=get_capabilities_health.reason_codes,
        details=get_capabilities_health.details,
    )
    health_engine.set_component(
        component="concierge_discovery_integration",
        required=True,
        state=concierge_discovery_health.state,
        reason_codes=concierge_discovery_health.reason_codes,
        details=concierge_discovery_health.details,
    )
    health_engine.set_component(
        component="concierge_voiceprofile_metadata_integration",
        required=True,
        state=concierge_voiceprofile_metadata_health.state,
        reason_codes=concierge_voiceprofile_metadata_health.reason_codes,
        details=concierge_voiceprofile_metadata_health.details,
    )
    health_engine.set_component(
        component="delete_supersede_voiceprint_operation",
        required=True,
        state=delete_supersede_health.state,
        reason_codes=delete_supersede_health.reason_codes,
        details=delete_supersede_health.details,
    )

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CONFIG_MANAGER: config_manager,
        DATA_CAPABILITY_REGISTRY: capability_registry,
        DATA_HEALTH_ENGINE: health_engine,
        DATA_STORAGE_PROVIDER: storage_provider,
        DATA_VOICEPRINT_REGISTRY: voiceprint_registry,
        DATA_VOICEPRINT_LIFECYCLE_MANAGER: lifecycle_manager,
        DATA_VOICEPRINT_REVISION_MANAGER: revision_manager,
        DATA_ARTIFACT_PERSISTENCE_ENGINE: persistence_engine,
        DATA_ARTIFACT_INTEGRITY_VALIDATOR: integrity_validator,
        DATA_SAMPLE_VALIDATION_PIPELINE: sample_validation_pipeline,
        DATA_QUALITY_SCORING_ENGINE: quality_scoring_engine,
        DATA_MODEL_EXECUTION_PROVIDER: model_execution_provider,
        DATA_GENERATION_ORCHESTRATOR: generation_orchestrator,
        DATA_GENERATE_VOICEPRINT_OPERATION: generate_voiceprint_operation,
        DATA_GET_VOICEPRINT_STATUS_OPERATION: get_voiceprint_status_operation,
        DATA_GET_CAPABILITIES_OPERATION: get_capabilities_operation,
        DATA_CONCIERGE_DISCOVERY_INTEGRATION: concierge_discovery_integration,
        DATA_CONCIERGE_VOICEPROFILE_METADATA_INTEGRATION: concierge_voiceprofile_metadata_integration,
        DATA_DELETE_SUPERSEDE_VOICEPRINT_OPERATION: delete_supersede_voiceprint_operation,
        DATA_HEALTH_TELEMETRY_PROVIDER: health_telemetry_provider,
        DATA_ATTRIBUTION_FOUNDATION: attribution_foundation,
        DATA_ATTRIBUTION_CONTEXT_STORE: attribution_context_store,
        DATA_IDENTITY_CONTEXT_GENERATOR: identity_context_generator,
        DATA_REPAIR_REGISTRY: repair_registry,
        DATA_REPAIR_RESOLVER: repair_resolver,
        DATA_STATUS: "not_implemented",
        DATA_MESSAGE: "Voice Identity runtime is not implemented yet.",
    }
    await async_register_services(hass)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload Voice Identity when the config entry changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Voice Identity config entry."""
    if DOMAIN in hass.data:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if isinstance(runtime, dict):
            config_manager = runtime.get(DATA_CONFIG_MANAGER)
            if isinstance(config_manager, VoiceIdentityConfigurationManager):
                config_manager.clear()

            capability_registry = runtime.get(DATA_CAPABILITY_REGISTRY)
            if isinstance(capability_registry, VoiceIdentityCapabilityRegistry):
                capability_registry.clear()

            health_engine = runtime.get(DATA_HEALTH_ENGINE)
            if isinstance(health_engine, VoiceIdentityHealthStateEngine):
                health_engine.clear()

            storage_provider = runtime.get(DATA_STORAGE_PROVIDER)
            if isinstance(storage_provider, LocalFileVoiceprintStorageProvider):
                storage_provider.clear()

            voiceprint_registry = runtime.get(DATA_VOICEPRINT_REGISTRY)
            if isinstance(voiceprint_registry, VoiceprintRegistry):
                voiceprint_registry.clear()

            lifecycle_manager = runtime.get(DATA_VOICEPRINT_LIFECYCLE_MANAGER)
            if isinstance(lifecycle_manager, VoiceprintLifecycleManager):
                lifecycle_manager.clear()

            revision_manager = runtime.get(DATA_VOICEPRINT_REVISION_MANAGER)
            if isinstance(revision_manager, VoiceprintRevisionManager):
                revision_manager.clear()

            persistence_engine = runtime.get(DATA_ARTIFACT_PERSISTENCE_ENGINE)
            if isinstance(persistence_engine, ArtifactPersistenceEngine):
                persistence_engine.clear()

            integrity_validator = runtime.get(DATA_ARTIFACT_INTEGRITY_VALIDATOR)
            if isinstance(integrity_validator, ArtifactIntegrityValidator):
                integrity_validator.clear()

            sample_validation_pipeline = runtime.get(DATA_SAMPLE_VALIDATION_PIPELINE)
            if isinstance(sample_validation_pipeline, SampleValidationPipelineProvider):
                sample_validation_pipeline.clear()

            quality_scoring_engine = runtime.get(DATA_QUALITY_SCORING_ENGINE)
            if isinstance(quality_scoring_engine, QualityScoringEngineProvider):
                quality_scoring_engine.clear()

            model_execution_provider = runtime.get(DATA_MODEL_EXECUTION_PROVIDER)
            if isinstance(model_execution_provider, ModelExecutionProviderRuntime):
                model_execution_provider.clear()

            generation_orchestrator = runtime.get(DATA_GENERATION_ORCHESTRATOR)
            if isinstance(generation_orchestrator, GenerationOrchestrator):
                generation_orchestrator.clear()

            generate_voiceprint_operation = runtime.get(DATA_GENERATE_VOICEPRINT_OPERATION)
            if isinstance(generate_voiceprint_operation, GenerateVoiceprintOperation):
                generate_voiceprint_operation.clear()

            get_voiceprint_status_operation = runtime.get(DATA_GET_VOICEPRINT_STATUS_OPERATION)
            if isinstance(get_voiceprint_status_operation, GetVoiceprintStatusOperation):
                get_voiceprint_status_operation.clear()

            get_capabilities_operation = runtime.get(DATA_GET_CAPABILITIES_OPERATION)
            if isinstance(get_capabilities_operation, GetCapabilitiesOperation):
                get_capabilities_operation.clear()

            concierge_discovery_integration = runtime.get(DATA_CONCIERGE_DISCOVERY_INTEGRATION)
            if isinstance(concierge_discovery_integration, ConciergeDiscoveryIntegration):
                concierge_discovery_integration.clear()

            concierge_voiceprofile_metadata_integration = runtime.get(
                DATA_CONCIERGE_VOICEPROFILE_METADATA_INTEGRATION
            )
            if isinstance(
                concierge_voiceprofile_metadata_integration,
                ConciergeVoiceProfileMetadataIntegration,
            ):
                concierge_voiceprofile_metadata_integration.clear()

            delete_supersede_voiceprint_operation = runtime.get(DATA_DELETE_SUPERSEDE_VOICEPRINT_OPERATION)
            if isinstance(delete_supersede_voiceprint_operation, DeleteSupersedeVoiceprintOperation):
                delete_supersede_voiceprint_operation.clear()

            health_telemetry_provider = runtime.get(DATA_HEALTH_TELEMETRY_PROVIDER)
            if isinstance(health_telemetry_provider, VoiceIdentityHealthTelemetryProvider):
                health_telemetry_provider.clear()

            attribution_foundation = runtime.get(DATA_ATTRIBUTION_FOUNDATION)
            if isinstance(attribution_foundation, SpeakerAttributionFoundation):
                attribution_foundation.clear()

        remaining_runtime_entries = [
            value
            for value in hass.data[DOMAIN].values()
            if isinstance(value, dict)
        ]
        if not remaining_runtime_entries:
            await async_unregister_services(hass)
    return True
