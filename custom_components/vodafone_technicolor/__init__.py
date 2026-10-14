"""Vodafone Station (Technicolor): router status, WiFi networks and connected devices."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = VodafoneCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
