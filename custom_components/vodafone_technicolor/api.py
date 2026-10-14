"""Client for Vodafone Station routers built by Technicolor (e.g. CGA6444VFES, Spanish firmware).

Uses the router's own web API (/api/v1/...) the same way its web interface does:
two-step PBKDF2 login, load the session menu, read the status pages, log out.
The router allows only one admin session, so this client never forces other sessions out.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field

import aiohttp

HEADERS = {
    # Without these the router answers the login with HTTP 500 / no salt.
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
# The web UI's own rule for device names.
HOSTNAME_RE = re.compile(r"^([a-z0-9](-*[a-z0-9])*)(([a-z0-9](-*[a-z0-9])*))*$", re.I)
# Minimum gap between logins. The router locks the web interface after bursts of logins,
# so even back-to-back actions (several renames) are spaced out.
MIN_LOGIN_INTERVAL = 10.0
NETWORK_BY_INTERFACE = {"Device.WiFi.SSID.1": "wifi_24", "Device.WiFi.SSID.2": "wifi_5", "Device.WiFi.SSID.3": "guest"}


class AuthError(Exception):
    """Wrong username or password."""


class RouterBusy(Exception):
    """Someone else is logged in to the router's web interface."""


class ConnectError(Exception):
    """Router unreachable or unexpected answer."""


def _pbkdf2(password: str, salt: str) -> str:
    # Same as the web UI: sjcl.misc.pbkdf2(password, salt, 1000, 128) with HMAC-SHA256, hex output.
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 1000, 16).hex()


def login_hash(password: str, salt: str, salt_webui: str) -> str:
    return password if salt == "none" else _pbkdf2(_pbkdf2(password, salt), salt_webui)


def _float(value) -> float | None:
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError):
        return None


def parse_status(data: dict) -> tuple[dict, dict]:
    """api/v1/sta_status -> (router, networks)."""
    router = {
        "uptime": int(data["uptime"]) if str(data.get("uptime", "")).isdigit() else None,
        "firmware": data.get("firmwareversion"),
        "hardware": data.get("hardwaretype"),
        "cpu": int(data["CPUUsage"]) if str(data.get("CPUUsage", "")).isdigit() else None,
        "memory_used_kb": int(data["MemoryUsage"]) if str(data.get("MemoryUsage", "")).isdigit() else None,
        "public_ip": data.get("internetipv4") or None,
        "lan_ip": data.get("lanipv4"),
        "lan_mac": (data.get("lanMAC") or "").upper() or None,
        "internet": data.get("operational"),
        "dns": [d.get("dns") for d in data.get("Dns_Tbl", []) if d.get("dns")],
        "ports": [
            {"port": n, "status": data.get(f"lanportstatus_{n}"), "speed_mbps": _float(data.get(f"lanportspeed_{n}"))}
            for n in range(1, 9)
            if f"lanportstatus_{n}" in data
        ],
    }

    def wifi(suffix: str, enabled_key: str) -> dict:
        return {
            "ssid": data.get(f"ssid{suffix}"),
            "enabled": str(data.get(enabled_key, "")).lower() == "true",
            "channel": data.get(f"channel{suffix}"),
            "bandwidth": data.get(f"bandwidth{suffix}"),
        }

    networks = {"wifi_24": wifi("", "wifistatus"), "wifi_5": wifi("_5", "wifistatus_5"), "guest": wifi("_G", "GuestEnable")}
    networks["wired"] = {"ssid": None, "enabled": True, "channel": None, "bandwidth": None}
    return router, networks


def parse_hosts(data: dict) -> tuple[list[dict], dict]:
    """api/v1/host -> (active clients, phone lines)."""
    link = {}
    for key in ("AssociatedDevices24", "AssociatedDevices5", "AssociatedDevicesGuest"):
        for a in data.get(key, []):
            rate = _float(a.get("linkRate"))
            link[a.get("macAddr", "").upper()] = round(rate / 1000) if rate else None  # kbit/s -> Mbit/s
    clients = []
    for h in data.get("hostTbl", []):
        if str(h.get("active", "")).lower() != "true":
            continue
        iface = h.get("layer1interface", "")
        network = NETWORK_BY_INTERFACE.get(iface) or ("wired" if "Ethernet" in iface else None)
        mac = h.get("physaddress", "").upper()
        rssi = _float(h.get("rssi"))
        port = iface.rsplit(".", 1)[-1] if iface.startswith("Device.Ethernet.Interface.") else None
        clients.append({
            "name": h.get("hostname") or h.get("alias") or None,
            "ip": h.get("ipaddress") or h.get("ipv41") or None,
            "mac": mac,
            "network": network,
            "port": int(port) if port and port.isdigit() else None,
            "signal": int(rssi) if rssi is not None and network != "wired" and rssi > -200 else None,
            "link_mbps": link.get(mac),
            "connected_s": int(h["activeTime"]) if str(h.get("activeTime", "")).isdigit() else None,
            "type": h.get("type") or None,
        })
    phones = {
        n: {"number": data.get(f"call_no{'' if n == 1 else n}") or None, "status": data.get(f"LineStatus{n}")}
        for n in (1, 2)
        if data.get(f"LineStatus{n}") not in (None, "", "Disabled")
    }
    return clients, phones


def parse_docsis(data: dict) -> dict:
    """api/v1/sta_docsis_status -> summary of the cable line."""
    down = [c for c in data.get("downstream", []) if _float(c.get("power")) is not None]
    up = [c for c in data.get("upstream", []) if _float(c.get("power")) is not None]

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 1) if values else None

    return {
        "status": data.get("operational"),
        "downstream_channels": len(down),
        "downstream_locked": sum(1 for c in down if str(c.get("locked", "")).lower() in ("locked", "true", "yes")),
        "downstream_power_avg": avg(_float(c.get("power")) for c in down),
        "downstream_snr_min": min((v for v in (_float(c.get("SNR")) for c in down) if v is not None), default=None),
        "upstream_channels": len(up),
        "upstream_power_avg": avg(_float(c.get("power")) for c in up),
    }


@dataclass
class RouterData:
    router: dict = field(default_factory=dict)
    networks: dict = field(default_factory=dict)
    clients: list = field(default_factory=list)
    phones: dict = field(default_factory=dict)
    docsis: dict = field(default_factory=dict)


class VodafoneTechnicolorClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, username: str, password: str) -> None:
        self._session, self._base = session, f"http://{host}/"
        self._username, self._password = username, password
        self._docsis: dict = {}
        self._polls = 0
        # One router session at a time: a poll and a rename share the cookie jar, and the router allows a single login.
        self._lock = asyncio.Lock()
        self._last_login = float("-inf")

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        try:
            async with self._session.request(method, self._base + path, data=data, headers={**HEADERS, "Referer": self._base},
                                             timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 401:
                    raise ConnectError(f"{path}: unauthorized")
                if resp.status != 200:
                    raise ConnectError(f"{path}: HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ConnectError(str(err)) from err

    async def _login(self) -> None:
        wait = self._last_login + MIN_LOGIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_login = time.monotonic()
        # No "logout" flag: if someone is using the web interface, back off instead of kicking them out.
        salts = await self._request("POST", "api/v1/session/login", {"username": self._username, "password": "seeksalthash"})
        if salts.get("message") == "MSG_LOGIN_150":
            raise RouterBusy
        if "salt" not in salts:
            # e.g. MSG_LOGIN_1: the router refuses logins (wrong credentials or a lockout, with a wait time in
            # data.failedAttempts). Treat it as an auth failure so Home Assistant stops polling and asks for the
            # password again, instead of retrying and extending the lockout.
            raise AuthError(f"login refused by the router: {salts.get('message')}")
        res = await self._request("POST", "api/v1/session/login", {
            "username": self._username,
            "password": login_hash(self._password, salts["salt"], salts["saltwebui"]),
        })
        if res.get("error") != "ok":
            raise AuthError(res.get("message"))
        await self._request("GET", "api/v1/session/menu")  # data pages answer 401 until the menu has been loaded

    async def _logout(self) -> None:
        try:
            await self._request("POST", "api/v1/session/logout", {})
        except ConnectError:
            pass  # the session expires on its own

    async def rename_device(self, mac: str, name: str) -> None:
        """Set the name the router shows for a device (same call as the web UI's edit dialog)."""
        if not HOSTNAME_RE.match(name):
            raise ValueError("Names may only contain letters, digits and hyphens")
        async with self._lock:
            await self._rename_device(mac, name)

    async def _rename_device(self, mac: str, name: str) -> None:
        self._session.cookie_jar.clear()
        await self._login()
        try:
            host = await self._request("GET", "api/v1/host")
            device = next((h for h in host["data"]["hostTbl"] if h.get("physaddress", "").upper() == mac.upper()), None)
            if device is None:
                raise ValueError(f"No device with MAC {mac}")
            data = {"HostName": name}
            if device.get("addresssource") == "Static" and device.get("staticId"):
                # Devices with a reserved IP also carry their name in the router's static DHCP table.
                data |= {"staticId": device["staticId"], "StaticHostName": name}
            async with self._session.post(self._base + f"api/v1/devices/{device['__id']}", data=data,
                                          headers={**HEADERS, "Referer": self._base, "X-CSRF-TOKEN": host.get("token", "")},
                                          timeout=aiohttp.ClientTimeout(total=20)) as resp:
                res = await resp.json(content_type=None)
            if res.get("error") != "ok":
                raise ConnectError(f"rename failed: {res.get('message')}")
        except (KeyError, TypeError) as err:
            raise ConnectError(f"unexpected data: {err}") from err
        finally:
            await self._logout()

    async def fetch(self) -> RouterData:
        async with self._lock:
            return await self._fetch()

    async def _fetch(self) -> RouterData:
        self._session.cookie_jar.clear()
        await self._login()
        try:
            router, networks = parse_status((await self._request("GET", "api/v1/sta_status"))["data"])
            clients, phones = parse_hosts((await self._request("GET", "api/v1/host"))["data"])
            # The cable line changes slowly: read it every 5th poll.
            if not self._docsis or self._polls % 5 == 0:
                self._docsis = parse_docsis((await self._request("GET", "api/v1/sta_docsis_status"))["data"])
            self._polls += 1
        except (KeyError, TypeError) as err:
            raise ConnectError(f"unexpected data: {err}") from err
        finally:
            await self._logout()
        return RouterData(router=router, networks=networks, clients=clients, phones=phones, docsis=self._docsis)
