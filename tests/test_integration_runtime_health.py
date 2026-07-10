from __future__ import annotations

import pytest

import custom_components.voice_identity as integration_module
from custom_components.voice_identity import async_setup_entry, async_unload_entry
from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import (
    VoiceIdentityConfigurationManager,
    VoiceIdentityConfigurationNotLoadedError,
)
from custom_components.voice_identity.const import (
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
    DATA_CAPABILITY_REGISTRY,
    DATA_CONFIG_MANAGER,
    DATA_HEALTH_ENGINE,
    DATA_STORAGE_PROVIDER,
    DATA_VOICEPRINT_LIFECYCLE_MANAGER,
    DATA_VOICEPRINT_REVISION_MANAGER,
    DATA_VOICEPRINT_REGISTRY,
    DOMAIN,
)
from custom_components.voice_identity.artifact_persistence import ArtifactPersistenceHealth
from custom_components.voice_identity.artifact_integrity import ArtifactIntegrityHealth
from custom_components.voice_identity.generation_orchestrator import GenerationOrchestratorHealth
from custom_components.voice_identity.generate_voiceprint_operation import GenerateVoiceprintOperation
from custom_components.voice_identity.voiceprint_status_metadata_operation import GetVoiceprintStatusOperation
from custom_components.voice_identity.capability_discovery_operation import GetCapabilitiesOperation
from custom_components.voice_identity.concierge_discovery_integration import ConciergeDiscoveryIntegration
from custom_components.voice_identity.concierge_voiceprofile_metadata_integration import (
    ConciergeVoiceProfileMetadataIntegration,
)
from custom_components.voice_identity.delete_supersede_voiceprint_operation import DeleteSupersedeVoiceprintOperation
from custom_components.voice_identity.health_state import HealthState, VoiceIdentityHealthStateEngine
from custom_components.voice_identity.model_execution import ModelExecutionProviderRuntime
from custom_components.voice_identity.quality_scoring import QualityScoringEngineProvider
from custom_components.voice_identity.sample_validation import SampleValidationPipelineProvider
from custom_components.voice_identity.storage_provider import LocalFileVoiceprintStorageProvider
from custom_components.voice_identity.voiceprint_lifecycle import VoiceprintLifecycleHealth
from custom_components.voice_identity.voiceprint_revision import VoiceprintRevisionHealth
from custom_components.voice_identity.voiceprint_registry import VoiceprintRegistryHealth


class _FakeVoiceprintRegistry:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    async def create(cls, *, hass, storage_provider):
        _ = hass
        _ = storage_provider
        return cls()

    async def validate_health(self):
        return VoiceprintRegistryHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_registry_ready",),
            details={"loaded": True, "record_count": 0},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _FakeVoiceprintLifecycleManager:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    def create(cls, *, registry):
        _ = registry
        return cls()

    async def validate_health(self):
        return VoiceprintLifecycleHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_lifecycle_ready",),
            details={"loaded": True, "record_count": 0},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _FakeVoiceprintRevisionManager:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    def create(cls, *, registry, lifecycle_manager):
        _ = registry
        _ = lifecycle_manager
        return cls()

    async def validate_health(self):
        return VoiceprintRevisionHealth(
            state=HealthState.HEALTHY,
            reason_codes=("voiceprint_revision_ready",),
            details={"loaded": True, "lineage_count": 0},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _FakeArtifactPersistenceEngine:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    def create(cls, *, storage_provider, registry, lifecycle_manager, revision_manager):
        _ = storage_provider
        _ = registry
        _ = lifecycle_manager
        _ = revision_manager
        return cls()

    async def validate_health(self):
        return ArtifactPersistenceHealth(
            state=HealthState.HEALTHY,
            reason_codes=("artifact_persistence_ready",),
            details={"loaded": True},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _FakeArtifactIntegrityValidator:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    def create(cls, *, storage_provider, registry, revision_manager):
        _ = storage_provider
        _ = registry
        _ = revision_manager
        return cls()

    async def validate_health(self):
        return ArtifactIntegrityHealth(
            state=HealthState.HEALTHY,
            reason_codes=("artifact_integrity_ready",),
            details={"loaded": True, "finding_count": 0},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _FakeGenerationOrchestrator:
    def __init__(self) -> None:
        self._cleared = False

    @classmethod
    def create(
        cls,
        *,
        config_manager,
        validation_pipeline,
        quality_engine,
        model_provider,
        persistence_engine,
        integrity_validator,
    ):
        _ = config_manager
        _ = validation_pipeline
        _ = quality_engine
        _ = model_provider
        _ = persistence_engine
        _ = integrity_validator
        return cls()

    async def validate_health(self):
        return GenerationOrchestratorHealth(
            state=HealthState.HEALTHY,
            reason_codes=("generation_orchestrator_ready",),
            details={"loaded": True, "tracked_generations": 0},
        )

    def clear(self):
        self._cleared = True

    @property
    def cleared(self) -> bool:
        return self._cleared


class _Hass:
    class _Config:
        def path(self, *parts: str) -> str:
            root = "r:/HomesPlatformRepos/voice_identity/.tmp_test_config"
            if not parts:
                return root
            return "/".join([root, *parts])

    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict[str, object]]] = {}
        self.config = self._Config()


class _Entry:
    entry_id = "entry-1"
    data: dict[str, object] = {}
    options: dict[str, object] = {}


@pytest.mark.asyncio
async def test_setup_stores_health_engine_in_runtime_data() -> None:
    original_registry_cls = integration_module.VoiceprintRegistry
    original_lifecycle_cls = integration_module.VoiceprintLifecycleManager
    original_revision_cls = integration_module.VoiceprintRevisionManager
    original_persistence_cls = integration_module.ArtifactPersistenceEngine
    original_integrity_cls = integration_module.ArtifactIntegrityValidator
    original_generation_cls = integration_module.GenerationOrchestrator
    integration_module.VoiceprintRegistry = _FakeVoiceprintRegistry
    integration_module.VoiceprintLifecycleManager = _FakeVoiceprintLifecycleManager
    integration_module.VoiceprintRevisionManager = _FakeVoiceprintRevisionManager
    integration_module.ArtifactPersistenceEngine = _FakeArtifactPersistenceEngine
    integration_module.ArtifactIntegrityValidator = _FakeArtifactIntegrityValidator
    integration_module.GenerationOrchestrator = _FakeGenerationOrchestrator
    hass = _Hass()
    entry = _Entry()

    try:
        result = await async_setup_entry(hass, entry)
    finally:
        integration_module.VoiceprintRegistry = original_registry_cls
        integration_module.VoiceprintLifecycleManager = original_lifecycle_cls
        integration_module.VoiceprintRevisionManager = original_revision_cls
        integration_module.ArtifactPersistenceEngine = original_persistence_cls
        integration_module.ArtifactIntegrityValidator = original_integrity_cls
        integration_module.GenerationOrchestrator = original_generation_cls

    assert result is True
    runtime = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(runtime[DATA_CONFIG_MANAGER], VoiceIdentityConfigurationManager)
    assert isinstance(runtime[DATA_CAPABILITY_REGISTRY], VoiceIdentityCapabilityRegistry)
    assert isinstance(runtime[DATA_HEALTH_ENGINE], VoiceIdentityHealthStateEngine)
    assert isinstance(runtime[DATA_STORAGE_PROVIDER], LocalFileVoiceprintStorageProvider)
    assert isinstance(runtime[DATA_VOICEPRINT_REGISTRY], _FakeVoiceprintRegistry)
    assert isinstance(runtime[DATA_VOICEPRINT_LIFECYCLE_MANAGER], _FakeVoiceprintLifecycleManager)
    assert isinstance(runtime[DATA_VOICEPRINT_REVISION_MANAGER], _FakeVoiceprintRevisionManager)
    assert isinstance(runtime[DATA_ARTIFACT_PERSISTENCE_ENGINE], _FakeArtifactPersistenceEngine)
    assert isinstance(runtime[DATA_ARTIFACT_INTEGRITY_VALIDATOR], _FakeArtifactIntegrityValidator)
    assert isinstance(runtime[DATA_SAMPLE_VALIDATION_PIPELINE], SampleValidationPipelineProvider)
    assert isinstance(runtime[DATA_QUALITY_SCORING_ENGINE], QualityScoringEngineProvider)
    assert isinstance(runtime[DATA_MODEL_EXECUTION_PROVIDER], ModelExecutionProviderRuntime)
    assert isinstance(runtime[DATA_GENERATION_ORCHESTRATOR], _FakeGenerationOrchestrator)
    assert isinstance(runtime[DATA_GENERATE_VOICEPRINT_OPERATION], GenerateVoiceprintOperation)
    assert isinstance(runtime[DATA_GET_VOICEPRINT_STATUS_OPERATION], GetVoiceprintStatusOperation)
    assert isinstance(runtime[DATA_GET_CAPABILITIES_OPERATION], GetCapabilitiesOperation)
    assert isinstance(runtime[DATA_CONCIERGE_DISCOVERY_INTEGRATION], ConciergeDiscoveryIntegration)
    assert isinstance(
        runtime[DATA_CONCIERGE_VOICEPROFILE_METADATA_INTEGRATION],
        ConciergeVoiceProfileMetadataIntegration,
    )
    assert isinstance(runtime[DATA_DELETE_SUPERSEDE_VOICEPRINT_OPERATION], DeleteSupersedeVoiceprintOperation)

    component_names = tuple(
        component.component for component in runtime[DATA_HEALTH_ENGINE].snapshot().components
    )
    assert "voiceprint_lifecycle_manager" in component_names
    assert "voiceprint_revision_manager" in component_names
    assert "artifact_persistence_engine" in component_names
    assert "artifact_integrity_validator" in component_names
    assert "sample_validation_pipeline" in component_names
    assert "quality_scoring_engine" in component_names
    assert "model_execution_provider" in component_names
    assert "generation_orchestrator" in component_names
    assert "generate_voiceprint_operation" in component_names
    assert "get_voiceprint_status_operation" in component_names
    assert "get_capabilities_operation" in component_names
    assert "concierge_discovery_integration" in component_names
    assert "concierge_voiceprofile_metadata_integration" in component_names
    assert "delete_supersede_voiceprint_operation" in component_names


@pytest.mark.asyncio
async def test_unload_clears_runtime_component_state() -> None:
    original_registry_cls = integration_module.VoiceprintRegistry
    original_lifecycle_cls = integration_module.VoiceprintLifecycleManager
    original_revision_cls = integration_module.VoiceprintRevisionManager
    original_persistence_cls = integration_module.ArtifactPersistenceEngine
    original_integrity_cls = integration_module.ArtifactIntegrityValidator
    original_generation_cls = integration_module.GenerationOrchestrator
    integration_module.VoiceprintRegistry = _FakeVoiceprintRegistry
    integration_module.VoiceprintLifecycleManager = _FakeVoiceprintLifecycleManager
    integration_module.VoiceprintRevisionManager = _FakeVoiceprintRevisionManager
    integration_module.ArtifactPersistenceEngine = _FakeArtifactPersistenceEngine
    integration_module.ArtifactIntegrityValidator = _FakeArtifactIntegrityValidator
    integration_module.GenerationOrchestrator = _FakeGenerationOrchestrator
    hass = _Hass()
    entry = _Entry()
    await async_setup_entry(hass, entry)

    runtime = hass.data[DOMAIN][entry.entry_id]
    config_manager = runtime[DATA_CONFIG_MANAGER]
    capability_registry = runtime[DATA_CAPABILITY_REGISTRY]
    health_engine = runtime[DATA_HEALTH_ENGINE]
    storage_provider = runtime[DATA_STORAGE_PROVIDER]
    voiceprint_registry = runtime[DATA_VOICEPRINT_REGISTRY]
    lifecycle_manager = runtime[DATA_VOICEPRINT_LIFECYCLE_MANAGER]
    revision_manager = runtime[DATA_VOICEPRINT_REVISION_MANAGER]
    persistence_engine = runtime[DATA_ARTIFACT_PERSISTENCE_ENGINE]
    integrity_validator = runtime[DATA_ARTIFACT_INTEGRITY_VALIDATOR]
    sample_validation_pipeline = runtime[DATA_SAMPLE_VALIDATION_PIPELINE]
    quality_scoring_engine = runtime[DATA_QUALITY_SCORING_ENGINE]
    model_execution_provider = runtime[DATA_MODEL_EXECUTION_PROVIDER]
    generation_orchestrator = runtime[DATA_GENERATION_ORCHESTRATOR]
    generate_voiceprint_operation = runtime[DATA_GENERATE_VOICEPRINT_OPERATION]
    get_voiceprint_status_operation = runtime[DATA_GET_VOICEPRINT_STATUS_OPERATION]
    get_capabilities_operation = runtime[DATA_GET_CAPABILITIES_OPERATION]
    concierge_discovery_integration = runtime[DATA_CONCIERGE_DISCOVERY_INTEGRATION]
    concierge_voiceprofile_metadata_integration = runtime[
        DATA_CONCIERGE_VOICEPROFILE_METADATA_INTEGRATION
    ]
    delete_supersede_voiceprint_operation = runtime[DATA_DELETE_SUPERSEDE_VOICEPRINT_OPERATION]

    assert isinstance(config_manager, VoiceIdentityConfigurationManager)
    assert isinstance(capability_registry, VoiceIdentityCapabilityRegistry)
    assert isinstance(health_engine, VoiceIdentityHealthStateEngine)
    assert isinstance(storage_provider, LocalFileVoiceprintStorageProvider)
    assert isinstance(voiceprint_registry, _FakeVoiceprintRegistry)
    assert isinstance(lifecycle_manager, _FakeVoiceprintLifecycleManager)
    assert isinstance(revision_manager, _FakeVoiceprintRevisionManager)
    assert isinstance(persistence_engine, _FakeArtifactPersistenceEngine)
    assert isinstance(integrity_validator, _FakeArtifactIntegrityValidator)
    assert isinstance(sample_validation_pipeline, SampleValidationPipelineProvider)
    assert isinstance(quality_scoring_engine, QualityScoringEngineProvider)
    assert isinstance(model_execution_provider, ModelExecutionProviderRuntime)
    assert isinstance(generation_orchestrator, _FakeGenerationOrchestrator)
    assert isinstance(generate_voiceprint_operation, GenerateVoiceprintOperation)
    assert isinstance(get_voiceprint_status_operation, GetVoiceprintStatusOperation)
    assert isinstance(get_capabilities_operation, GetCapabilitiesOperation)
    assert isinstance(concierge_discovery_integration, ConciergeDiscoveryIntegration)
    assert isinstance(
        concierge_voiceprofile_metadata_integration,
        ConciergeVoiceProfileMetadataIntegration,
    )
    assert isinstance(delete_supersede_voiceprint_operation, DeleteSupersedeVoiceprintOperation)

    try:
        result = await async_unload_entry(hass, entry)
    finally:
        integration_module.VoiceprintRegistry = original_registry_cls
        integration_module.VoiceprintLifecycleManager = original_lifecycle_cls
        integration_module.VoiceprintRevisionManager = original_revision_cls
        integration_module.ArtifactPersistenceEngine = original_persistence_cls
        integration_module.ArtifactIntegrityValidator = original_integrity_cls
        integration_module.GenerationOrchestrator = original_generation_cls

    assert result is True
    assert entry.entry_id not in hass.data[DOMAIN]

    with pytest.raises(VoiceIdentityConfigurationNotLoadedError):
        _ = config_manager.config

    assert capability_registry.supports("capability_registry") is False
    assert health_engine.snapshot().components == ()
    assert storage_provider.cleared is True
    assert voiceprint_registry.cleared is True
    assert lifecycle_manager.cleared is True
    assert revision_manager.cleared is True
    assert persistence_engine.cleared is True
    assert integrity_validator.cleared is True
    assert sample_validation_pipeline.cleared is True
    assert quality_scoring_engine.cleared is True
    assert model_execution_provider.cleared is True
    assert generation_orchestrator.cleared is True
    assert generate_voiceprint_operation.cleared is True
    assert get_voiceprint_status_operation.cleared is True
    assert get_capabilities_operation.cleared is True
    assert concierge_discovery_integration.cleared is True
    assert concierge_voiceprofile_metadata_integration.cleared is True
    assert delete_supersede_voiceprint_operation.cleared is True


@pytest.mark.asyncio
async def test_unload_does_not_disrupt_other_entry_runtime_data() -> None:
    original_registry_cls = integration_module.VoiceprintRegistry
    original_lifecycle_cls = integration_module.VoiceprintLifecycleManager
    original_revision_cls = integration_module.VoiceprintRevisionManager
    original_persistence_cls = integration_module.ArtifactPersistenceEngine
    original_integrity_cls = integration_module.ArtifactIntegrityValidator
    original_generation_cls = integration_module.GenerationOrchestrator
    integration_module.VoiceprintRegistry = _FakeVoiceprintRegistry
    integration_module.VoiceprintLifecycleManager = _FakeVoiceprintLifecycleManager
    integration_module.VoiceprintRevisionManager = _FakeVoiceprintRevisionManager
    integration_module.ArtifactPersistenceEngine = _FakeArtifactPersistenceEngine
    integration_module.ArtifactIntegrityValidator = _FakeArtifactIntegrityValidator
    integration_module.GenerationOrchestrator = _FakeGenerationOrchestrator
    hass = _Hass()
    entry = _Entry()
    await async_setup_entry(hass, entry)

    hass.data[DOMAIN]["other-entry"] = {"preserve": True}

    try:
        result = await async_unload_entry(hass, entry)
    finally:
        integration_module.VoiceprintRegistry = original_registry_cls
        integration_module.VoiceprintLifecycleManager = original_lifecycle_cls
        integration_module.VoiceprintRevisionManager = original_revision_cls
        integration_module.ArtifactPersistenceEngine = original_persistence_cls
        integration_module.ArtifactIntegrityValidator = original_integrity_cls
        integration_module.GenerationOrchestrator = original_generation_cls

    assert result is True
    assert "other-entry" in hass.data[DOMAIN]
    assert hass.data[DOMAIN]["other-entry"]["preserve"] is True