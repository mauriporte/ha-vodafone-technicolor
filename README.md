# Vodafone Station (Technicolor) for Home Assistant

A Home Assistant custom integration for **Vodafone Station routers built by Technicolor**, such as the **CGA6444VFES** that Vodafone Spain supplies. It shows the router's status, the cable line, the WiFi networks and every connected device, grouped by network.

Home Assistant's built-in *Vodafone Station* integration does not work with the Spanish firmware: it expects status fields this firmware doesn't have, and after a failed update it leaves the router's single admin session open, which locks you out of the web interface. This integration was written for that firmware and is careful with the session.

## Features

| Area | What you get |
|---|---|
| Router | Public IP (and DNS servers), LAN IP, MAC, firmware, last boot, CPU and memory use, Ethernet port status/speed |
| Internet | Connected/disconnected (binary sensor) and the router's status text |
| Cable line (DOCSIS) | Line status; channel counts, average power and minimum SNR as attributes |
| WiFi networks | 2.4 GHz, 5 GHz and guest: enabled (binary sensors), name, channel, bandwidth |
| Devices per network | One sensor each for 2.4 GHz, 5 GHz, guest and wired: the number of active devices, with the list (name, IP, MAC, signal, link speed, Ethernet port, connected time, type) as attributes |
| Phone | Status of each enabled VoIP line |
| Session | A diagnostic binary sensor that turns on while someone is using the router's web interface |

The router's API has no per-device traffic counters. For overall internet traffic, use Home Assistant's built-in **UPnP/IGD** integration on the same router.

## How it works

Once a minute the integration does what the router's web interface does:

1. Logs in with the router's two-step PBKDF2 login.
2. Loads the session menu (the data pages refuse requests until it has).
3. Reads `api/v1/sta_status`, `api/v1/host` and, every fifth poll, `api/v1/sta_docsis_status`.
4. Logs out.

### One session at a time

The router allows **only one logged-in admin**. The integration never forces another session out. If you're logged in to the web interface in a browser, the integration skips its update, keeps the last values, and turns on **Web interface in use**. It picks up again once you log out, or your browser session times out.

The reverse also applies: if you open the web interface during the few seconds the integration is logged in, the router asks whether to log out the other user. Answering yes is harmless.

### If the router refuses the login

The router locks its web interface for a while after repeated logins it doesn't like. To avoid making that worse, the integration:

- Never retries a refused login. It stops updating, and Home Assistant shows a **Reconfigure / re-authenticate** prompt where you confirm the password.
- Keeps at least 10 seconds between logins.

## Installation

There are two ways to install it. **HACS is the easiest** and also gives you updates. Use the manual method if you don't have HACS.

### Option A: HACS (recommended)

1. In Home Assistant, open **HACS**, then the **⋮** menu (top right) → **Custom repositories**.
2. Paste this repository's URL, choose the category **Integration**, and click **Add**.
3. Search HACS for **Vodafone Station (Technicolor)**, open it and click **Download**.
4. Restart Home Assistant (**Settings → System**, power button at the top right → **Restart Home Assistant**).

### Option B: Manual

You copy one folder, `vodafone_technicolor`, into a folder called `custom_components` inside Home Assistant's **configuration folder**. That's the folder containing `configuration.yaml`.

**1. Find your configuration folder.** It depends on how Home Assistant is installed. Not sure which one you have? Go to **Settings → System → Repairs**, open the **⋮** menu → **System information**, and look at *Installation type*.

| Installation type | Where the configuration folder is | Easiest way to copy files there |
|---|---|---|
| **Home Assistant OS** (Raspberry Pi, Home Assistant Green/Yellow, virtual machine) | `/config` | The **Samba share** add-on (it appears as the `config` network share on your computer), or the **File editor** / **Studio Code Server** add-ons |
| **Home Assistant Supervised** | `/usr/share/hassio/homeassistant` on the host (`/config` inside add-ons) | Same add-ons as above, or SSH to the host |
| **Home Assistant Container** (Docker, including NAS systems like ZimaOS, CasaOS, Unraid, Synology, TrueNAS) | The host folder mapped to `/config` in the container. Find it in your `docker-compose.yml` (`volumes: - /some/host/path:/config`), in the app's settings on your NAS, or with `docker inspect homeassistant` | Your NAS file manager, a network share, or `scp` to the host |
| **Home Assistant Core** (Python virtual environment) | Usually `~/.homeassistant` for the user that runs Home Assistant | Copy directly on that machine |

**2. Copy the folder.** Download this repository (green **Code** button → **Download ZIP**) and unzip it. Copy the folder `custom_components/vodafone_technicolor` from the ZIP into your configuration folder. If `custom_components` doesn't exist there yet, create it. The result must look like this:

```
<configuration folder>/              ← the folder that contains configuration.yaml
├── configuration.yaml
├── custom_components/               ← create it if it doesn't exist
│   └── vodafone_technicolor/        ← copied from this repository
│       ├── __init__.py
│       ├── api.py
│       ├── manifest.json
│       ├── ...
│       └── translations/
└── ...
```

Common mistakes:
- Nesting one folder too deep (`custom_components/vodafone_technicolor/vodafone_technicolor/…`). `manifest.json` must sit directly inside `custom_components/vodafone_technicolor/`.
- Copying the whole repository instead of just the `vodafone_technicolor` folder.
- On Docker, copying into a folder on the host that isn't the one mapped to `/config`.

**3. Restart Home Assistant** (**Settings → System**, power button at the top right → **Restart Home Assistant**). Custom integrations are only loaded at startup.

## Configuration

**Log out of the router's web interface in your browser first** (one session at a time), then go to **Settings → Devices & services → Add integration → Vodafone Station (Technicolor)**:

| Field | Value |
|---|---|
| Host | The router's address, usually `192.168.0.1` |
| Username | Usually `vodafone` |
| Password | The web interface password |

If you mistype the password, wait a few seconds before trying again: the router briefly refuses logins after a failed attempt.

## Entities

With the default device name **Vodafone Station**:

| Entity | Notes |
|---|---|
| `binary_sensor.vodafone_station_internet` | On when the router reports `OPERATIONAL` |
| `sensor.vodafone_station_public_ip` | Attribute `dns` |
| `sensor.vodafone_station_cable_line` | Attributes: `downstream_channels`, `downstream_locked`, `downstream_power_avg`, `downstream_snr_min`, `upstream_channels`, `upstream_power_avg` |
| `sensor.vodafone_station_wifi_2_4_ghz_devices`, `…_wifi_5_ghz_devices`, `…_guest_wifi_devices`, `…_wired_devices` | State = active devices. Attributes: `ssid`, `enabled`, `channel`, `bandwidth`, `devices` (each with `name`, `ip`, `mac`, `signal`, `link_mbps`, `port`, `connected_s`, `type`) |
| `binary_sensor.vodafone_station_wifi_2_4_ghz_enabled`, `…_wifi_5_ghz_enabled`, `…_guest_wifi_enabled` | |
| `sensor.vodafone_station_phone_line_1` | Only for enabled lines |
| `sensor.vodafone_station_lan_ip` | Attribute `ports` (Ethernet port status and speed) |
| `sensor.vodafone_station_mac`, `…_firmware`, `…_last_boot`, `…_cpu_usage`, `…_memory_used`, `…_internet_status` | Diagnostic |
| `binary_sensor.vodafone_station_web_interface_in_use` | Diagnostic; on while updates are paused because someone else is logged in |

## Dashboard example

A Markdown card listing the devices on a network:

```yaml
type: markdown
title: WiFi 5 GHz
content: >-
  {% set n = states.sensor.vodafone_station_wifi_5_ghz_devices %}
  **{{ n.attributes.ssid }}** · channel {{ n.attributes.channel }} · {{ n.state }} device(s)

  | Name | IP | MAC | Signal | Link |
  |---|---|---|---|---|
  {% for d in n.attributes.devices -%}
  | {{ d.name or '—' }} | {{ d.ip or '—' }} | {{ d.mac }} | {{ d.signal ~ ' dBm' if d.signal is not none else '—' }} | {{ d.link_mbps ~ ' Mbps' if d.link_mbps else '—' }} |
  {% endfor %}
```

## Limitations

- **Tested hardware:** CGA6444VFES with firmware 19.3B70-1.1.16A (Vodafone Spain). Other Technicolor Vodafone Stations with the same web API should work. Please open an issue with a sample if one doesn't.
- **No downstream values:** this firmware leaves the downstream channel fields of the cable line empty, so only upstream values are shown.
- **Device names** are whatever the router knows (DHCP hostname or a name set in the router), and can be out of date.
- **HTTP only**, like the router's web interface. Keep Home Assistant and the router on a trusted LAN.

## Development

```bash
python -m pytest tests                                       # parser tests, no Home Assistant needed (needs aiohttp)
VF_PASSWORD=... python scripts/live_check.py                 # query a real router (VF_HOST / VF_USER optional)
```

## License

MIT, see [LICENSE](LICENSE).
