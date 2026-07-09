"""Coordinator scaffold for Voice Identity integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant


class VoiceIdentityCoordinator:
    """Minimal coordinator placeholder for future runtime state."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_refresh(self) -> None:
        """Refresh coordinator state.

        Not implemented yet.
        """
