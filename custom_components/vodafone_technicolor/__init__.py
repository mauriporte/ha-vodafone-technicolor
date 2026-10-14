"""Vodafone Station (Technicolor): router status, WiFi networks and connected devices."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, ConnectError, RouterBusy, RouterData, VodafoneTechnicolorClient

DOMAIN = "vodafone_technicolor"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)


class VodafoneCoordinator(DataUpdateCoordinator[RouterData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=60), config_entry=entry)
        # Own cookie jar: the router session cookie must not be shared with other integrations.
        session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
        d = entry.data
        self.client = VodafoneTechnicolorClient(session, d[CONF_HOST], d[CONF_USERNAME], d[CONF_PASSWORD])
        self.busy = False  # True while someone else is logged in to the web interface

    async def _async_update_data(self) -> RouterData:
        try:
            data = await self.client.fetch()
        except RouterBusy:
            self.busy = True
            if self.data is None:
                raise UpdateFailed("Someone is logged in to the router's web interface") from None
            return self.data  # keep the last values instead of kicking the user out
        except AuthError as err:
            raise ConfigEntryAuthFailed from err
        except ConnectError as err:
            raise UpdateFailed(str(err)) from err
        self.busy = False
        return data


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the rename_device action."""

    async def rename_device(call: ServiceCall) -> None:
        mac, name = call.data["mac"], call.data["name"]
        coordinators = [e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)]
        if not coordinators:
            raise HomeAssistantError("No Vodafone Station (Technicolor) router is set up")
        # Use the router that currently lists this MAC (normally there is only one).
        target = next((c for c in coordinators if any(d["mac"] == mac.upper() for d in c.data.clients)), coordinators[0])
        try:
            await target.client.rename_device(mac, name)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except RouterBusy as err:
            raise HomeAssistantError("Someone is logged in to the router's web interface; try again later") from err
        except (AuthError, ConnectError) as err:
            raise HomeAssistantError(f"Rename failed: {err}") from err
        await target.async_request_refresh()

    if not hass.services.has_service(DOMAIN, "rename_device"):
        hass.services.async_register(DOMAIN, "rename_device", rename_device, schema=RENAME_SCHEMA)
    return True


RENAME_SCHEMA = vol.Schema({vol.Required("mac"): cv.string, vol.Required("name"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = VodafoneCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
