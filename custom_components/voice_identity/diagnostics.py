"""Diagnostics scaffold for Voice Identity integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict:
    """Return allowlisted diagnostics scaffold payload."""
    return {
        "status": "not_implemented",
        "message": "Voice Identity diagnostics are not implemented yet.",
        "entry_id": config_entry.entry_id,
    }
