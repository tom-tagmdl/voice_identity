from __future__ import annotations

from dataclasses import asdict

import pytest

from custom_components.voice_identity.capability_registry import VoiceIdentityCapabilityRegistry
from custom_components.voice_identity.configuration import VoiceIdentityConfigurationManager
from custom_components.voice_identity.health_state import HealthState
from custom_components.voice_identity.capability_discovery_operation import (
	CompatibilityDiscoveryRequest,
	CompatibilityStatus,
	GetCapabilitiesFailureCategory,
	GetCapabilitiesOperation,
	GetCapabilitiesRequest,
	GetVersionDiscoveryRequest,
)


class _Entry:
	entry_id = "entry"
	data: dict[str, object] = {}
	options: dict[str, object] = {}


class _UnavailableCapabilityRegistry:
	def supports(self, capability_name: str, *, config_schema_version: int | None = None) -> bool:
		_ = capability_name
		_ = config_schema_version
		return False

	def snapshot(self):
		raise RuntimeError("not available")


class _RaisingCapabilityRegistry:
	def supports(self, capability_name: str, *, config_schema_version: int | None = None) -> bool:
		_ = config_schema_version
		return capability_name == "capability_registry"

	def snapshot(self):
		raise RuntimeError("Traceback: internal registry object at C:/secret/path")


class _MutationGuardCapabilityRegistry:
	def __init__(self, *, delegate: VoiceIdentityCapabilityRegistry) -> None:
		self._delegate = delegate
		self.register_calls = 0
		self.clear_calls = 0

	def supports(self, capability_name: str, *, config_schema_version: int | None = None) -> bool:
		return self._delegate.supports(
			capability_name,
			config_schema_version=config_schema_version,
		)

	def snapshot(self):
		return self._delegate.snapshot()

	def register(self, descriptor):
		_ = descriptor
		self.register_calls += 1
		raise AssertionError("mutation not allowed")

	def clear(self):
		self.clear_calls += 1
		raise AssertionError("mutation not allowed")


def _build_registry() -> VoiceIdentityCapabilityRegistry:
	manager = VoiceIdentityConfigurationManager()
	manager.load_from_entry(_Entry())
	return VoiceIdentityCapabilityRegistry.from_configuration_manager(manager)


@pytest.mark.asyncio
async def test_successful_capability_discovery() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is True
	assert result.service_name == "voice_identity"
	assert result.service_version == "0.1.0"
	assert result.discovery_contract_version == 1
	assert result.supported_contract_versions == (1,)
	assert result.supported_schema_versions == (1,)
	assert result.compatibility_status is CompatibilityStatus.COMPATIBLE
	assert len(result.capabilities) > 0


@pytest.mark.asyncio
async def test_successful_version_discovery() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.get_versions(GetVersionDiscoveryRequest.create())

	assert result.success is True
	assert result.discovery_contract_version == 1
	assert result.metadata_schema_version == 1
	assert result.capability_discovery_schema_version == 1
	assert result.status_contract_version == 1
	assert result.supported_contract_versions == (1,)
	assert result.supported_schema_versions == (1,)


@pytest.mark.asyncio
async def test_supported_capability_projection() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is True
	names = tuple(item.capability_name for item in result.capabilities if item.supported)
	assert "voiceprint_operation_generate" in names


@pytest.mark.asyncio
async def test_schema_version_unsupported() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(
		GetCapabilitiesRequest.create(requested_schema_version=99),
	)

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.SCHEMA_VERSION_UNSUPPORTED
	assert result.reason_code == "schema_version_unsupported"
	assert result.requested_schema_version == 99


@pytest.mark.asyncio
async def test_contract_version_unsupported() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(
		GetCapabilitiesRequest.create(requested_contract_version=99),
	)

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.COMPATIBILITY_VERSION_UNSUPPORTED
	assert result.reason_code == "compatibility_version_unsupported"
	assert result.requested_contract_version == 99


@pytest.mark.asyncio
async def test_capability_registry_unavailable() -> None:
	operation = GetCapabilitiesOperation.create(
		capability_registry=_UnavailableCapabilityRegistry(),
	)

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.CAPABILITY_REGISTRY_UNAVAILABLE
	assert result.reason_code == "capability_registry_unavailable"


@pytest.mark.asyncio
async def test_operation_not_loaded() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())
	operation.clear()

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED
	assert result.reason_code == "operation_not_loaded"


@pytest.mark.asyncio
async def test_operation_not_loaded_for_versions() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())
	operation.clear()

	result = await operation.get_versions(GetVersionDiscoveryRequest.create())

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED


@pytest.mark.asyncio
async def test_internal_error_normalization() -> None:
	operation = GetCapabilitiesOperation.create(
		capability_registry=_RaisingCapabilityRegistry(),
	)

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.OPERATION_INTERNAL_ERROR
	assert result.reason_code == "operation_internal_error"


@pytest.mark.asyncio
async def test_public_projection_excludes_implementation_details() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is True
	payload = asdict(result)
	dumped = str(payload)
	assert "_capabilities" not in dumped
	assert "<" not in dumped
	assert "object at" not in dumped


@pytest.mark.asyncio
async def test_version_discovery_reports_compatible_status() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.get_versions(GetVersionDiscoveryRequest.create())

	assert result.success is True
	assert result.compatibility_status is CompatibilityStatus.COMPATIBLE
	assert result.compatibility_details.upgrade_guidance == "no_action_required"


@pytest.mark.asyncio
async def test_compatibility_discovery_compatible() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.evaluate_compatibility(
		CompatibilityDiscoveryRequest.create(
			requested_contract_version=1,
			requested_schema_version=1,
		)
	)

	assert result.success is True
	assert result.compatibility_status is CompatibilityStatus.COMPATIBLE


@pytest.mark.asyncio
async def test_compatibility_discovery_partially_compatible() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.evaluate_compatibility(
		CompatibilityDiscoveryRequest.create(
			requested_contract_version=1,
			requested_schema_version=99,
		)
	)

	assert result.success is True
	assert result.compatibility_status is CompatibilityStatus.PARTIALLY_COMPATIBLE
	assert result.compatibility_details.upgrade_guidance == "upgrade_recommended"


@pytest.mark.asyncio
async def test_compatibility_discovery_unsupported() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.evaluate_compatibility(
		CompatibilityDiscoveryRequest.create(
			requested_contract_version=99,
			requested_schema_version=99,
		)
	)

	assert result.success is True
	assert result.compatibility_status is CompatibilityStatus.UNSUPPORTED
	assert result.compatibility_details.upgrade_guidance == "select_supported_versions"


@pytest.mark.asyncio
async def test_compatibility_discovery_not_loaded() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())
	operation.clear()

	result = await operation.evaluate_compatibility(CompatibilityDiscoveryRequest.create())

	assert result.success is False
	assert result.failure_category is GetCapabilitiesFailureCategory.OPERATION_NOT_LOADED


@pytest.mark.asyncio
async def test_no_capability_mutation() -> None:
	guarded_registry = _MutationGuardCapabilityRegistry(delegate=_build_registry())
	operation = GetCapabilitiesOperation.create(capability_registry=guarded_registry)

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is True
	assert guarded_registry.register_calls == 0
	assert guarded_registry.clear_calls == 0


@pytest.mark.asyncio
async def test_health_readiness() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	health = await operation.validate_health()

	assert health.state is HealthState.HEALTHY
	assert health.reason_codes == ("capability_discovery_ready", "version_discovery_ready")


@pytest.mark.asyncio
async def test_health_operation_not_loaded() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())
	operation.clear()

	health = await operation.validate_health()

	assert health.state is HealthState.UNAVAILABLE
	assert health.reason_codes == ("operation_not_loaded",)


@pytest.mark.asyncio
async def test_privacy_boundary_enforcement() -> None:
	operation = GetCapabilitiesOperation.create(
		capability_registry=_RaisingCapabilityRegistry(),
	)

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is False
	rendered = str(result)
	assert "Traceback" not in rendered
	assert "secret" not in rendered
	assert "path" not in rendered


@pytest.mark.asyncio
async def test_consumer_compatibility_shape() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	result = await operation.execute(GetCapabilitiesRequest.create())

	assert result.success is True
	payload = asdict(result)
	assert payload["service_name"] == "voice_identity"
	assert isinstance(payload["capabilities"], tuple)
	assert isinstance(payload["supported_contract_versions"], tuple)
	assert isinstance(payload["supported_schema_versions"], tuple)


@pytest.mark.asyncio
async def test_stable_read_model_behavior() -> None:
	operation = GetCapabilitiesOperation.create(capability_registry=_build_registry())

	first = await operation.execute(GetCapabilitiesRequest.create())
	second = await operation.execute(GetCapabilitiesRequest.create())

	assert first == second
