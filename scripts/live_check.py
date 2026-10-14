"""Query a real router with the integration's client, without Home Assistant.

Usage: VF_HOST=192.168.0.1 VF_USER=vodafone VF_PASSWORD=... python scripts/live_check.py
Log out of the router's web interface first (the router allows one session at a time).
"""
import asyncio
import os
import sys

import aiohttp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "vodafone_technicolor"))
import api  # noqa: E402


async def main() -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        client = api.VodafoneTechnicolorClient(session, os.environ.get("VF_HOST", "192.168.0.1"), os.environ.get("VF_USER", "vodafone"), os.environ["VF_PASSWORD"])
        data = await client.fetch()
    print("router:", data.router)
    print("networks:", data.networks)
    print("docsis:", data.docsis)
    print("phones:", list(data.phones))
    for c in data.clients:
        print(f"  {c['network']:8} {str(c['name']):24} {str(c['ip']):15} {c['mac']} signal={c['signal']} link={c['link_mbps']} port={c['port']}")


asyncio.run(main())
