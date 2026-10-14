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

    async def async_step_reauth(self, entry_data):
        """The router refused the login: polling has stopped until the user confirms the password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            session = async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
            client = VodafoneTechnicolorClient(session, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD])
            try:
                await client.fetch()
            except RouterBusy:
                errors["base"] = "router_busy"
            except AuthError:
                errors["base"] = "invalid_auth"
            except ConnectError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}), errors=errors)
