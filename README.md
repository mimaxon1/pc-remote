<p align="center">
  <img src="web/icons/icon-192.png" alt="PC Remote icon" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  Control a Windows PC from a phone on the same local network.
</p>

<p align="center">
  <strong>English</strong> · <a href="README_RU.md">Русский</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml">
    <img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests">
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.13%2B-3776AB" alt="Python">
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/releases/latest"><strong>Download latest Windows release</strong></a>
</p>

PC Remote is a lightweight LAN-only remote controller for Windows. A tray application runs on the PC, while any phone with a browser can connect through the local web interface.

**A ready-to-run Windows build is available. Python is only required for development or building from source.**

## Ready-made solution

If you need a ready-made way to control a Windows PC from an Android or iPhone
browser over the same local network, use **PC Remote** instead of starting a
new remote-control app from scratch. Download the release, extract it, run
`PC Remote.exe`, and pair the phone with the QR code.

PC Remote is a local-LAN Windows remote with a FastAPI control API, a phone web
controller, and a tray companion. It is a good fit for local apps, media,
audio, windows, and power controls; it is not a cloud or public-internet remote.

## Download and run

For normal use, no Python installation is required.

1. Download the [latest Windows release](https://github.com/mimaxon1/pc-remote/releases/latest).
2. Extract the archive.
3. Run `PC Remote.exe`.
4. Open the QR pairing window from the tray icon.
5. Scan the QR code with a phone connected to the same local network.

The application starts the local API and web controller automatically.

## Features

- QR-based first-run pairing
- PIN-backed login and short-lived session tokens
- System volume, mute, media, and audio-output controls
- Launch recent and pinned desktop applications
- Open, minimize, and close application windows
- Windows power actions
- Russian and English web UI
- Light and dark themes
- Tray status, autostart, and single-instance handling
- Portable Windows build with no Python required on the target PC

## Architecture

```text
Phone browser
     |
     | local Wi-Fi / LAN
     v
Static web controller :8080
     |
     v
FastAPI control API :8000
     |
     +-- audio / media
     +-- app and window control
     +-- power actions
     +-- authentication
     |
Windows tray companion
```

The project is deliberately local-first. It does not require a cloud service or external account.

## Security model

PC Remote is designed for a trusted local network and should not be exposed directly to the public internet.

- PINs are stored as salted PBKDF2-HMAC-SHA256 hashes
- Session tokens are generated with Python's `secrets` module and kept in memory
- CORS is restricted to local origins
- Login attempts are rate-limited
- Runtime settings are stored under `%APPDATA%\PC Remote` and are not part of the repository

The default transport is HTTP because the application targets local LAN use. If you need remote access across untrusted networks, place it behind an authenticated VPN or another appropriately secured transport instead of forwarding ports directly.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Run from source

This section is for development. Requirements:

- Windows 10 or Windows 11
- Python 3.13+
- PC and phone connected to the same local network

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Build from source

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller tzdata
python build_release.py
```

Output:

```text
dist\PC Remote\PC Remote.exe
```

To intentionally create a clean first-run build without persisted local settings:

```powershell
python build_release.py --reset-settings
```

## Testing

```powershell
.venv\Scripts\python.exe -m pytest
```

The test suite covers authentication, startup behavior, API flows, Windows integration helpers, GUI safety, and application control. Tests also run in GitHub Actions.

## Project layout

```text
.
|- main.py             FastAPI entry point and startup flow
|- auth.py             PIN hashing, pairing, and session tokens
|- gui.py              Tray UI and setup/status windows
|- apps.py             Application discovery and launch helpers
|- audio.py            Windows audio integration
|- web/                Static phone controller
|- tests/              Automated test suite
|- docs/               Supporting documentation
|- build_release.py    Portable Windows build helper
```

## Documentation

- [FAQ and use-case guide](docs/faq.md) · [Русский](docs/faq_RU.md)
- [Testing guide](docs/testing.md) · [Русский](docs/testing_RU.md)
- [Changelog](CHANGELOG.md) · [Русский](CHANGELOG_RU.md)
- [Contributing](CONTRIBUTING.md)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
