<p align="center">
  <img src="web/icons/icon-192.png" alt="PC Remote icon" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  <strong>Control your Windows PC from any phone browser.</strong><br>
  No mobile app. No account. No cloud. Run it, scan a QR code, and control the PC over your local network.
</p>

<p align="center">
  <a href="README.md"><strong>English</strong></a> · <a href="README_RU.md">Русский</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/releases/latest"><strong>Download for Windows</strong></a>
  ·
  <a href="docs/faq.md">FAQ</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml"><img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6" alt="Windows 10/11">
  <img src="https://img.shields.io/github/license/mimaxon1/pc-remote" alt="License">
  <img src="https://img.shields.io/github/v/release/mimaxon1/pc-remote" alt="Latest release">
</p>

PC Remote is a lightweight, open-source Windows remote that turns any Android or iPhone browser into a local control panel for your PC. It is designed for people who want a simple local-first alternative to cloud-connected remote-control apps.

Use it from the couch, beside a TV, during a presentation, or anywhere else on the same Wi-Fi/LAN.

## Why PC Remote?

- **No phone app required** — open the controller in any modern browser.
- **No account or cloud service** — traffic stays on your local network.
- **Fast pairing** — run PC Remote and scan the QR code.
- **Ready-made Windows build** — Python is not required for normal use.
- **Useful everyday controls** — apps, windows, volume, media, audio output, and power actions.
- **Open source** — inspect it, modify it, or self-host it on your own PC.

If you are looking for an open-source, browser-based Windows remote or a lightweight local alternative to tools such as Unified Remote, PC Remote is built for that use case.

## Quick start

1. Open the [latest release](https://github.com/mimaxon1/pc-remote/releases/latest).
2. Download the Windows build.
3. Run `PC Remote.exe`.
4. Open the QR pairing window from the tray icon.
5. Scan the QR code using a phone connected to the same local network.
6. Start controlling the PC from the browser.

Older releases may provide a portable ZIP only. New tagged releases are configured to publish both a Windows installer and a portable ZIP automatically.

## What you can control

- System volume and mute
- Media playback controls
- Audio-output device selection
- Recent and pinned applications
- Launching desktop applications
- Opening, minimizing, and closing application windows
- Windows power actions
- Autostart and tray behavior
- Light and dark themes
- Russian and English web UI

## Good fit for

- Couch / HTPC control
- Media PCs connected to a TV
- Presentation and demo PCs
- Local gaming or streaming setups
- A second-screen control panel
- Home-lab and self-hosted Windows setups

## Local-first by design

```text
Phone browser
     |
     | local Wi-Fi / LAN
     v
Web controller :8080
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

PC Remote does not require an external account or cloud backend.

## Security model

PC Remote is intended for a trusted local network. Do **not** expose its ports directly to the public internet.

- PINs are stored as salted PBKDF2-HMAC-SHA256 hashes
- Session tokens are generated with Python's `secrets` module and kept in memory
- CORS is restricted to local origins
- Login attempts are rate-limited
- Runtime settings are stored under `%APPDATA%\PC Remote`

The default transport is HTTP because the application targets local LAN use. For access from outside your home network, use an authenticated VPN or another appropriately secured transport instead of direct port forwarding.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Windows packaging

The project supports two release formats:

- **Installer** — normal per-user Windows installation with Start Menu shortcut and optional desktop shortcut.
- **Portable ZIP** — extract and run without installation.

Tagged releases (`v*`) are built automatically by GitHub Actions. The release workflow runs tests, builds the PyInstaller bundle, creates the Inno Setup installer, creates the portable ZIP, and publishes SHA-256 checksums.

## Run from source

Requirements:

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

Portable output:

```text
dist\PC Remote\PC Remote.exe
```

To intentionally create a clean first-run build without persisted local settings:

```powershell
python build_release.py --reset-settings
```

To create the installer after the portable build, compile [`installer/PC-Remote.iss`](installer/PC-Remote.iss) with Inno Setup 6.

## Testing

```powershell
.venv\Scripts\python.exe -m pytest
```

Tests also run in GitHub Actions.

## Project layout

```text
.
|- main.py                 FastAPI entry point and startup flow
|- auth.py                 PIN hashing, pairing, and session tokens
|- gui.py                  Tray UI and setup/status windows
|- apps.py                 Application discovery and launch helpers
|- audio.py                Windows audio integration
|- web/                    Phone web controller
|- tests/                  Automated test suite
|- installer/              Windows installer definition
|- docs/                   Documentation and launch material
|- build_release.py        Portable Windows build helper
```

## Documentation

- [FAQ and use-case guide](docs/faq.md) · [Русский](docs/faq_RU.md)
- [Testing guide](docs/testing.md) · [Русский](docs/testing_RU.md)
- [Launch / promotion kit](docs/PROMOTION.md)
- [Changelog](CHANGELOG.md) · [Русский](CHANGELOG_RU.md)
- [Contributing](CONTRIBUTING.md)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
