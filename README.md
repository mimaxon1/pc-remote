<p align="center">
  <img src="web/icons/icon-192.png" alt="PC Remote icon" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  Control a Windows PC from your phone over the local network with QR onboarding,
  a tray companion app, and a lightweight web controller.
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml">
    <img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg" alt="Tests">
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.13%2B-3776AB" alt="Python">
</p>

Current release target: `v1.4.0`

## Overview

PC Remote runs three pieces together:

- A FastAPI API on port `8000`
- A static web controller on port `8080`
- A Windows tray app for QR pairing, settings, and status

The project is designed for local LAN use. It is not intended to be exposed
directly to the public internet.

## Highlights

- QR-based first-run setup
- Passwordless QR reconnect after pairing
- 4-digit PIN login flow
- Volume, mute, and media controls
- Quick launch for recent and pinned desktop apps
- Open, minimize, and close app windows from the controller
- Light and dark theme toggle in the web UI
- Russian and English UI language switch
- Adaptive offline detection with retry backoff
- Tray-based autostart and single-instance protection

## Requirements

- Windows 10 or Windows 11
- Python 3.13+ for source runs and builds
- A phone and PC connected to the same local network

## Quick Start

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

`tkinter` is not installed from pip here; it ships with the standard Windows
Python distribution used by the tray GUI.

## Build A Portable Bundle

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller tzdata
python build_release.py
```

Output:

- `dist\PC Remote\PC Remote.exe`

## Testing

Run the full suite from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest
```

Documentation for test layout, targeted runs, and troubleshooting lives in
[docs/testing.md](docs/testing.md).

## Documentation

- [Documentation hub](docs/README.md)
- [Testing guide](docs/testing.md)
- [Roadmap](docs/roadmap.md)
- [Implementation notes](docs/implementation-notes.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Project Layout

```text
.
|- main.py                  FastAPI entry point and startup flow
|- auth.py                  PIN, QR pairing, and token management
|- gui.py                   Tray UI and setup/status windows
|- apps.py                  App discovery, quick launch, and window actions
|- audio.py                 Windows audio device and volume helpers
|- web/                     Static controller UI and icons
|- tests/                   Automated test suite
|- docs/                    Supporting documentation
|- build_release.py         Portable Windows bundle helper
```

## Configuration Notes

- Runtime settings live in `%APPDATA%\PC Remote\settings.json`
- Logs are written to `%APPDATA%\PC Remote\pc-remote.log`
- `/health` exposes a lightweight status endpoint for diagnostics
- If QR links resolve to the wrong local address, set
  `PC_REMOTE_PUBLIC_HOST=192.168.x.x` before launch
- If the phone cannot connect, allow ports `8000` and `8080` in Windows Firewall

## Troubleshooting

- `ModuleNotFoundError: pystray`: install dependencies again and rebuild
- `PermissionError` under `dist\PC Remote`: close the running app before rebuilding
- Pairing opens an unreachable address: override the host with `PC_REMOTE_PUBLIC_HOST`

## Development Notes

- Tests are expected to pass on Windows and currently run in GitHub Actions
- Supporting docs live under `docs/` to keep the repository root clean
- Temporary analysis files such as `tmp_*` are intentionally ignored and do not
  ship with the public repository
