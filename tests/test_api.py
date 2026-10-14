"""Parser tests for custom_components/vodafone_technicolor/api.py (no Home Assistant needed).

Run: python -m pytest tests   (or: python tests/test_api.py)
Sample data uses documentation IP ranges and locally administered MAC addresses.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "vodafone_technicolor"))
import api  # noqa: E402

STATUS = {
    "uptime": "190910", "firmwareversion": "19.3B70-1.1.16A", "hardwaretype": "1.0.0", "CPUUsage": "39", "MemoryUsage": "155908",
    "internetipv4": "198.51.100.7", "lanipv4": "192.168.0.1", "lanMAC": "02:00:00:00:00:01", "operational": "OPERATIONAL",
    "Dns_Tbl": [{"__id": "1", "dns": "198.51.100.53", "Type": "DHCPv4"}],
    "lanportstatus_1": "Up", "lanportspeed_1": "1000", "lanportstatus_2": "Down", "lanportspeed_2": "",
    "wifistatus": "true", "channel": "11", "bandwidth": "40MHz", "ssid": "Home",
    "wifistatus_5": "true", "channel_5": "52", "bandwidth_5": "80MHz", "ssid_5": "Home-5G",
    "GuestEnable": "false", "ssid_G": "Home-guest",
}

HOST = {
    "call_no": "sip:+00000000000@example.invalid", "LineStatus1": "Up", "LineStatus2": "Disabled",
    "AssociatedDevices24": [{"macAddr": "02:00:00:00:00:0A", "linkRate": "72000"}],
    "AssociatedDevices5": [{"macAddr": "02:00:00:00:00:0B", "linkRate": "866000"}],
    "hostTbl": [
        {"hostname": "plug", "alias": "", "physaddress": "02:00:00:00:00:0a", "ipaddress": "192.168.0.50", "layer1interface": "Device.WiFi.SSID.1",
         "active": "true", "activeTime": "54288", "rssi": "-45", "type": "VOX"},
        {"hostname": "", "alias": "laptop", "physaddress": "02:00:00:00:00:0b", "ipaddress": "192.168.0.51", "layer1interface": "Device.WiFi.SSID.2",
         "active": "true", "activeTime": "100", "rssi": "-60", "type": "Laptop"},
        {"hostname": "nas", "alias": "", "physaddress": "02:00:00:00:00:0c", "ipaddress": "192.168.0.60", "layer1interface": "Device.Ethernet.Interface.3",
         "active": "true", "activeTime": "3786", "rssi": "-200", "type": "VOX"},
        {"hostname": "old-phone", "alias": "", "physaddress": "02:00:00:00:00:0d", "ipaddress": "192.168.0.52", "layer1interface": "Device.WiFi.SSID.1",
         "active": "false", "activeTime": "0", "rssi": "-70", "type": "MobilePhone"},
    ],
}


def test_login_hash_matches_web_ui():
    # sjcl.misc.pbkdf2(pw, salt, 1000, 128) -> hex, applied twice (salt, then saltwebui)
    first = hashlib.pbkdf2_hmac("sha256", b"secret", b"abc", 1000, 16).hex()
    assert api.login_hash("secret", "abc", "xyz") == hashlib.pbkdf2_hmac("sha256", first.encode(), b"xyz", 1000, 16).hex()
    assert api.login_hash("secret", "none", "xyz") == "secret"  # routers without hashing


def test_status():
    router, nets = api.parse_status(STATUS)
    assert router["uptime"] == 190910 and router["cpu"] == 39 and router["memory_used_kb"] == 155908
    assert router["public_ip"] == "198.51.100.7" and router["lan_mac"] == "02:00:00:00:00:01" and router["internet"] == "OPERATIONAL"
    assert router["dns"] == ["198.51.100.53"]
    assert router["ports"] == [{"port": 1, "status": "Up", "speed_mbps": 1000.0}, {"port": 2, "status": "Down", "speed_mbps": None}]
    assert nets["wifi_24"] == {"ssid": "Home", "enabled": True, "channel": "11", "bandwidth": "40MHz"}
    assert nets["wifi_5"]["ssid"] == "Home-5G" and nets["guest"]["enabled"] is False


def test_hosts():
    clients, phones = api.parse_hosts(HOST)
    by_name = {c["name"]: c for c in clients}
    assert set(by_name) == {"plug", "laptop", "nas"}  # inactive devices are skipped
    assert by_name["plug"] == {"name": "plug", "ip": "192.168.0.50", "mac": "02:00:00:00:00:0A", "network": "wifi_24", "port": None,
                               "signal": -45, "link_mbps": 72, "connected_s": 54288, "type": "VOX"}
    assert by_name["laptop"]["network"] == "wifi_5" and by_name["laptop"]["link_mbps"] == 866
    assert by_name["nas"]["network"] == "wired" and by_name["nas"]["port"] == 3 and by_name["nas"]["signal"] is None
    assert phones == {1: {"number": "sip:+00000000000@example.invalid", "status": "Up"}}


def test_docsis():
    d = api.parse_docsis({
        "operational": "OPERATIONAL",
        "downstream": [{"power": "", "SNR": "", "locked": ""}, {"power": "3.2 dBmV", "SNR": "40.1 dB", "locked": "Locked"}],
        "upstream": [{"power": "35.4 dBmV"}, {"power": "35.0 dBmV"}],
    })
    assert d == {"status": "OPERATIONAL", "downstream_channels": 1, "downstream_locked": 1, "downstream_power_avg": 3.2,
                 "downstream_snr_min": 40.1, "upstream_channels": 2, "upstream_power_avg": 35.2}


def test_hostname_rule():
    for ok in ("LivingRoomLamp", "tv-1", "a"):
        assert api.HOSTNAME_RE.match(ok), ok
    for bad in ("Living room", "lámpara", "-tv", "tv-", "a_b", ""):
        assert not api.HOSTNAME_RE.match(bad), bad


def test_poll_and_rename_never_overlap():
    import asyncio

    async def run():
        client = api.VodafoneTechnicolorClient(None, "192.0.2.1", "u", "p")
        active, overlaps = 0, []

        async def busy(*_):
            nonlocal active
            active += 1
            overlaps.append(active)
            await asyncio.sleep(0.01)
            active -= 1

        client._fetch = busy
        client._rename_device = busy
        await asyncio.gather(client.fetch(), client.rename_device("02:00:00:00:00:0A", "lamp"), client.fetch())
        return overlaps

    assert max(asyncio.run(run())) == 1  # the router allows a single session, so never two at once


def test_refused_login_stops_instead_of_retrying():
    import asyncio

    async def run():
        client = api.VodafoneTechnicolorClient(None, "192.0.2.1", "u", "p")
        answers = [{"error": "error", "message": "MSG_LOGIN_1", "data": {"failedAttempts": 2}}]

        async def fake_request(*_a, **_k):
            return answers.pop(0)

        client._request = fake_request
        try:
            await client._login()
        except api.AuthError:
            return True  # AuthError -> ConfigEntryAuthFailed -> polling stops, user is asked for the password
        return False

    assert asyncio.run(run())


def test_logins_are_spaced_out():
    import asyncio
    import time

    async def run():
        client = api.VodafoneTechnicolorClient(None, "192.0.2.1", "u", "p")
        api.MIN_LOGIN_INTERVAL, saved = 0.3, api.MIN_LOGIN_INTERVAL
        stamps = []

        async def fake_request(_m, path, *_a, **_k):
            if path.endswith("login"):
                stamps.append(time.monotonic())
                return {"error": "error", "message": "MSG_LOGIN_150"}
            return {}

        client._request = fake_request
        for _ in range(2):
            try:
                await client._login()
            except api.RouterBusy:
                pass
        api.MIN_LOGIN_INTERVAL = saved
        return stamps[1] - stamps[0]

    assert asyncio.run(run()) >= 0.29


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
