"""Config flow for Voice Identity integration scaffold."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class VoiceIdentityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Identity."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create a basic config entry for scaffold setup."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=None)

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Voice Identity", data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VoiceIdentityOptionsFlow(config_entry)


class VoiceIdentityOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Voice Identity scaffold."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=None)
