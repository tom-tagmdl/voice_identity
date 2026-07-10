"""Diagnostics entrypoint for Voice Identity integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .diagnostics_provider import VoiceIdentityDiagnosticsProvider, build_runtime_context, minimal_runtime_presence


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict:
    """Return allowlisted diagnostics payload for one config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if not isinstance(runtime, dict):
        return {
            "entry_id": config_entry.entry_id,
            "source": "config_entry_diagnostics",
            "runtime_loaded": False,
            "reason_code": "runtime_unavailable",
        }

    provider = VoiceIdentityDiagnosticsProvider()
    payload = await provider.collect(
        context=build_runtime_context(entry_id=config_entry.entry_id, runtime=runtime),
        source="config_entry_diagnostics",
    )
    payload["runtime_presence"] = minimal_runtime_presence(runtime)
    return payload
