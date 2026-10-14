from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from . import DOMAIN
from .api import AuthError, ConnectError, RouterBusy, VodafoneTechnicolorClient

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.0.1"): str,
        vol.Required(CONF_USERNAME, default="vodafone"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class VodafoneTechnicolorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            session = async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
            client = VodafoneTechnicolorClient(session, user_input[CONF_HOST], user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                data = await client.fetch()
            except RouterBusy:
                errors["base"] = "router_busy"
            except AuthError:
                errors["base"] = "invalid_auth"
            except ConnectError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id((data.router.get("lan_mac") or user_input[CONF_HOST]).lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Vodafone Station {user_input[CONF_HOST]}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
