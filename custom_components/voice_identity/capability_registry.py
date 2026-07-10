"""Capability registry for Voice Identity integration.

Capabilities describe what the platform supports. Configuration controls whether
implemented capabilities are enabled at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .configuration import VoiceIdentityConfiguration, VoiceIdentityConfigurationManager

REGISTRY_SCHEMA_VERSION = 1


class CapabilityCategory(StrEnum):
    """High-level capability grouping."""

    FOUNDATION = "foundation"
    VOICEPRINT = "voiceprint"
    ATTRIBUTION = "attribution"
    HEALTH = "health"
    DIAGNOSTICS = "diagnostics"
    CONCIERGE = "concierge"
    OPERATIONS = "operations"


class CapabilityMaturity(StrEnum):
    """Capability implementation maturity."""

    IMPLEMENTED = "implemented"
    PLANNED = "planned"


@dataclass(slots=True, frozen=True)
class CapabilityDescriptor:
    """Metadata for one discoverable capability."""

    name: str
    description: str
    category: CapabilityCategory
    maturity: CapabilityMaturity
    introduced_config_schema_version: int = 1


@dataclass(slots=True, frozen=True)
class CapabilityStatus:
    """Resolved capability status for consumers."""

    descriptor: CapabilityDescriptor
    supported: bool
    enabled: bool


@dataclass(slots=True, frozen=True)
class CapabilitySnapshot:
    """Versioned snapshot payload of discovered capabilities."""

    registry_schema_version: int
    config_schema_version: int
    capabilities: tuple[CapabilityStatus, ...]


class VoiceIdentityCapabilityRegistryError(Exception):
    """Base exception for capability registry failures."""


class VoiceIdentityCapabilityDuplicateError(VoiceIdentityCapabilityRegistryError):
    """Raised when registering a capability that already exists."""


class VoiceIdentityCapabilityVersionError(VoiceIdentityCapabilityRegistryError):
    """Raised when capability version metadata is invalid."""


class VoiceIdentityCapabilityRegistry:
    """Authoritative capability discovery surface for Voice Identity."""

    def __init__(self, config: VoiceIdentityConfiguration) -> None:
        self._config = config
        self._capabilities: dict[str, CapabilityDescriptor] = {}

    @classmethod
    def from_configuration_manager(
        cls,
        manager: VoiceIdentityConfigurationManager,
    ) -> VoiceIdentityCapabilityRegistry:
        """Construct registry using authoritative configuration manager."""
        registry = cls(manager.config)
        registry.register_defaults()
        return registry

    def register_defaults(self) -> None:
        """Register baseline capability catalog from architecture and roadmap."""
        for descriptor in _default_capabilities():
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Register one capability descriptor."""
        if descriptor.introduced_config_schema_version < 1:
            raise VoiceIdentityCapabilityVersionError(
                "introduced_config_schema_version must be >= 1."
            )
        if descriptor.name in self._capabilities:
            raise VoiceIdentityCapabilityDuplicateError(
                f"Capability '{descriptor.name}' is already registered."
            )
        self._capabilities[descriptor.name] = descriptor

    def supports(self, capability_name: str, *, config_schema_version: int | None = None) -> bool:
        """Return true when a capability is known and version-supported."""
        descriptor = self._capabilities.get(capability_name)
        if descriptor is None:
            return False

        effective_version = (
            config_schema_version
            if config_schema_version is not None
            else self._config.config_schema_version
        )
        return descriptor.introduced_config_schema_version <= effective_version

    def status(
        self,
        capability_name: str,
        *,
        config_schema_version: int | None = None,
    ) -> CapabilityStatus | None:
        """Return resolved status for a capability, or None when unknown."""
        descriptor = self._capabilities.get(capability_name)
        if descriptor is None:
            return None

        supported = self.supports(
            capability_name,
            config_schema_version=config_schema_version,
        )
        enabled = supported and self._is_enabled(descriptor)
        return CapabilityStatus(
            descriptor=descriptor,
            supported=supported,
            enabled=enabled,
        )

    def list_capabilities(self, *, config_schema_version: int | None = None) -> tuple[CapabilityStatus, ...]:
        """Return stable-sorted capability status list."""
        statuses = [
            self.status(name, config_schema_version=config_schema_version)
            for name in sorted(self._capabilities)
        ]
        return tuple(status for status in statuses if status is not None)

    def snapshot(self, *, config_schema_version: int | None = None) -> CapabilitySnapshot:
        """Return a versioned registry snapshot for consumers."""
        effective_version = (
            config_schema_version
            if config_schema_version is not None
            else self._config.config_schema_version
        )
        return CapabilitySnapshot(
            registry_schema_version=REGISTRY_SCHEMA_VERSION,
            config_schema_version=effective_version,
            capabilities=self.list_capabilities(config_schema_version=effective_version),
        )

    def update_configuration(self, config: VoiceIdentityConfiguration) -> None:
        """Update runtime configuration reference used for enablement evaluation."""
        self._config = config

    def clear(self) -> None:
        """Clear registered capabilities for unload lifecycle."""
        self._capabilities.clear()

    def _is_enabled(self, descriptor: CapabilityDescriptor) -> bool:
        if descriptor.maturity is not CapabilityMaturity.IMPLEMENTED:
            return False

        if not self._config.service.enabled:
            return False

        if descriptor.name == "diagnostics":
            return self._config.diagnostics.enabled

        if descriptor.name == "repairs":
            return self._config.feature_flags.enable_repairs

        if descriptor.name in {
            "runtime_attribution",
            "identity_context_generation",
            "attribution_operation",
            "attribution_request_validation",
            "attribution_availability",
        }:
            return self._config.feature_flags.enable_runtime_attribution

        return True


def _default_capabilities() -> tuple[CapabilityDescriptor, ...]:
    """Return capability catalog grounded in ADR, roadmap, contracts, and backlog."""
    return (
        CapabilityDescriptor(
            name="configuration_manager",
            description="Typed configuration loading, validation, and reload handling.",
            category=CapabilityCategory.FOUNDATION,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="capability_registry",
            description="Version-aware capability discovery and metadata snapshotting.",
            category=CapabilityCategory.FOUNDATION,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_generation",
            description="Generate durable voiceprints from enrollment samples.",
            category=CapabilityCategory.VOICEPRINT,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="voiceprint_storage",
            description="Provider-owned voiceprint artifact persistence.",
            category=CapabilityCategory.VOICEPRINT,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_registry",
            description="Metadata registry for immutable voiceprint artifact references.",
            category=CapabilityCategory.VOICEPRINT,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_revision_management",
            description="Voiceprint revision lineage and supersede lifecycle.",
            category=CapabilityCategory.VOICEPRINT,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_lifecycle_management",
            description="Lifecycle transition management for voiceprint metadata records.",
            category=CapabilityCategory.VOICEPRINT,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_operation_generate",
            description="Service operation for GenerateVoiceprint.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="artifact_persistence_engine",
            description="Persistence orchestration for encrypted voiceprint artifacts and metadata.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="artifact_integrity_validation",
            description="Read-only integrity validation for artifacts, metadata, and revision chains.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="generation_orchestrator",
            description="Workflow orchestration across validation, quality, model, persistence, and integrity.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="sample_validation_pipeline",
            description="Validation of generation request references and readiness metadata.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="quality_scoring_engine",
            description="Deterministic quality scoring and threshold evaluation for generation readiness.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="model_execution_provider",
            description="Provider abstraction for model execution and representation generation.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_operation_status_metadata",
            description="Service operations for GetVoiceprintStatus and metadata.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="capability_discovery_operation",
            description="Service operation for capability and version discovery.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="concierge_discovery_integration",
            description="Concierge-facing integration for discovery, compatibility, and availability projection.",
            category=CapabilityCategory.CONCIERGE,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="concierge_voiceprofile_metadata_integration",
            description="Concierge-facing integration for voiceprofile metadata and readiness projection.",
            category=CapabilityCategory.CONCIERGE,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="voiceprint_operation_delete_supersede",
            description="Service operations for delete and supersede lifecycle.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="runtime_attribution",
            description="Runtime speaker attribution capability.",
            category=CapabilityCategory.ATTRIBUTION,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="identity_context_generation",
            description="Identity Context generation for coordinator consumption.",
            category=CapabilityCategory.ATTRIBUTION,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="attribution_operation",
            description="Service operation for AttributeSpeaker.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="attribution_request_validation",
            description="Service operation for ValidateAttributionRequest.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="attribution_availability",
            description="Service operation for GetAttributionAvailability.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="health_state_engine",
            description="Service/provider/model/storage health state aggregation.",
            category=CapabilityCategory.HEALTH,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="health_service",
            description="Service health projection operation.",
            category=CapabilityCategory.HEALTH,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="health_provider",
            description="Provider health projection operation.",
            category=CapabilityCategory.HEALTH,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="health_model",
            description="Model health projection operation.",
            category=CapabilityCategory.HEALTH,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="health_storage",
            description="Storage health projection operation.",
            category=CapabilityCategory.HEALTH,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="diagnostics",
            description="Diagnostics provider with allowlist-safe outputs.",
            category=CapabilityCategory.DIAGNOSTICS,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="repairs",
            description="Repairs framework for actionable issue handling.",
            category=CapabilityCategory.DIAGNOSTICS,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="concierge_discovery",
            description="Concierge discovery integration.",
            category=CapabilityCategory.CONCIERGE,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="concierge_voiceprofile_metadata",
            description="Concierge VoiceProfile metadata integration.",
            category=CapabilityCategory.CONCIERGE,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="concierge_enrollment",
            description="Concierge enrollment workflow integration.",
            category=CapabilityCategory.CONCIERGE,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="discovery_supported_models",
            description="Capability operation for supported model discovery.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="discovery_contract_versions",
            description="Capability operation for contract version discovery.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
        CapabilityDescriptor(
            name="discovery_schema_versions",
            description="Capability operation for schema version discovery.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.PLANNED,
        ),
        CapabilityDescriptor(
            name="discovery_feature_availability",
            description="Capability operation for feature availability discovery.",
            category=CapabilityCategory.OPERATIONS,
            maturity=CapabilityMaturity.IMPLEMENTED,
        ),
    )
