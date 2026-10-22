"""Download diagnostics: the router's last raw answers, to see which fields and pages are available."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME


def _secret_keys(value, found: set) -> set:
    # Wi-Fi keys and similar sit under firmware-specific names, so match by name instead of listing them.
    if isinstance(value, dict):
        for k, v in value.items():
            low = k.lower()
            if any(word in low for word in ("pass", "psk", "key", "secret", "salt", "token")) or low.endswith("pin"):
                found.add(k)
            _secret_keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _secret_keys(v, found)
    return found


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    raw = entry.runtime_data.client.raw
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_USERNAME, CONF_PASSWORD}),
        "raw": async_redact_data(raw, _secret_keys(raw, set())),
    }
