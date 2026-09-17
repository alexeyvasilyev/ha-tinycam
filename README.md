# tinyCam Monitor for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration for
[tinyCam Monitor PRO](https://tinycammonitor.com/), built on top of its
official [web server REST API](https://github.com/alexeyvasilyev/tinycam-api).

tinyCam Monitor turns an Android device into a video surveillance hub that
aggregates many IP/RTSP/ONVIF cameras. This integration lets Home Assistant
talk to that hub directly, so every camera tinyCam already knows about shows
up in Home Assistant automatically — no need to configure each camera twice.

## Features

For every camera reported by tinyCam:

- **Camera** entity — live snapshot and RTSP stream (`camera.<name>`)
- **Motion** binary sensor
- **LED / IR light mode** select (on / off / auto)
- **Detection** event entity — fires on new recorded motion / person /
  vehicle / pet / face / audio / pin events
- PTZ services: `tinycam.ptz_move`, `tinycam.ptz_stop`, `tinycam.ptz_home`,
  `tinycam.ptz_goto_preset`, `tinycam.ptz_save_preset`

For the tinyCam server (hub device) itself:

- Sensors: CPU usage/frequency, memory used/available, battery level,
  uptime, network in/out, storage used/available, live connections
- Switches: background mode, power safe mode, notifications
- Select: stream profile (main / sub / auto)
- Button: reboot device (requires root on the Android device)
- Service: `tinycam.set_notifications` (on/off, optionally scoped to a tag)

Cameras added in tinyCam are discovered on the next successful poll. Removed
cameras become unavailable; if they return with the same ID, their existing
entities are reused.

All data is polled locally over HTTP(S) — nothing goes through the cloud.

## Requirements

- tinyCam Monitor PRO with the **web server enabled** (Settings → Web/RTSP
  server) and reachable from Home Assistant.
- Admin username/password configured in tinyCam if you want status sensors,
  switches, PTZ, LED control and reboot — guest access only exposes the
  camera list, live streams and event history. With guest access, admin-only
  controls and status sensors remain unavailable while cameras and detection
  events continue to work.

## Installation

### Option A: HACS (custom repository)

Use this if the integration's code lives in its own Git repository (e.g.
on GitHub) that HACS can pull updates from.

1. In Home Assistant, open **HACS → Integrations → ⋮ (top right) → Custom
   repositories**.
2. Paste the repository URL, set category to **Integration**, click **Add**.
3. Find **tinyCam Monitor** in HACS, click **Download** (install).
4. Restart Home Assistant: **Settings → System → Restart**.
5. Continue with [Configuration](#configuration) below.

### Option B: Manual copy

Copy the `custom_components/tinycam` folder from this project into your
Home Assistant config directory, so the result is
`<config>/custom_components/tinycam/...` (containing `__init__.py`,
`manifest.json`, etc. directly inside `tinycam/`).

How you get files into `<config>` depends on your installation type:

- **Home Assistant OS / Supervised** — easiest via the **Samba share** or
  **File editor / Studio Code Server** add-on, or over SSH with the
  **Terminal & SSH** add-on:

  ```bash
  scp -r custom_components/tinycam root@<HA_IP>:/config/custom_components/
  ```

  (add-on SSH access usually runs as `root`; port is `22` unless you
  changed it in the add-on's configuration).

- **Home Assistant Container / Core (Docker, venv, etc.)** — copy into the
  host directory you mounted/configured as `config`, e.g.:

  ```bash
  scp -r custom_components/tinycam user@<HOST>:/path/to/ha/config/custom_components/
  ```

If `custom_components` doesn't exist yet in your config directory, create
it first — it's a plain folder, not something Home Assistant generates
automatically.

Then:

1. Restart Home Assistant: **Settings → System → Restart** (or
   `ha core restart` over SSH).
2. Continue with [Configuration](#configuration) below.

## Configuration

Once the files are in place and Home Assistant has restarted, add the
integration through the UI:

**Settings → Devices & Services → Add Integration** → search for
**tinyCam Monitor** → select it.

(If it doesn't show up, do a hard-refresh of the browser page (Ctrl/Cmd +
Shift + R) — the integration list is cached client-side.)

You'll need:

| Field | Description |
|---|---|
| Host | IP address or hostname of the Android device running tinyCam |
| Port | Web server port, default `8083` |
| Username / Password | Optional; required for admin-only endpoints |
| Use HTTPS | Enable if tinyCam's web server has "Use HTTPS" turned on |
| Verify SSL certificate | Disable for tinyCam's self-signed certificate |

The polling interval (default 30s) can be changed afterwards from the
integration's **Configure** options.

## Notes and limitations

- **Stream profile** and **LED mode** are *optimistic* entities: the tinyCam
  API does not report their current value back, so these selects simply
  remember the last value Home Assistant sent (restored across restarts).
- Reboot requires root access on the Android device (tinyCam's own
  requirement, not this integration's).

## Services

See **Developer Tools → Services** in Home Assistant for the full list and
field descriptions (`tinycam.ptz_move`, `tinycam.ptz_stop`,
`tinycam.ptz_home`, `tinycam.ptz_goto_preset`, `tinycam.ptz_save_preset`,
`tinycam.set_notifications`).

## Development tests

The regression suite uses real Home Assistant entity classes and simulated API
responses. With Python 3.14:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

It covers guest access, unavailable motion readings, dynamic camera discovery,
individual event publication, history catch-up, timestamp ties, task cleanup,
and empty-password authentication. Tests do not contact a real tinyCam server.

## API reference

This integration implements the endpoints documented at
[alexeyvasilyev/tinycam-api](https://github.com/alexeyvasilyev/tinycam-api).

