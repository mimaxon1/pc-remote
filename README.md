<p align="center">
  <img src="web/icons/icon-192.png" alt="PC Remote icon" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  <strong>Control a Windows PC or Mac from any phone browser.</strong><br>
  No mobile app. No account. No cloud. Run it, scan a QR code, and control the PC over your local network.
</p>

<p align="center">
  <a href="README.md"><strong>English</strong></a> · <a href="README_RU.md">Русский</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/releases/latest"><strong>Download for Windows or macOS</strong></a>
  ·
  <a href="docs/faq.md">FAQ</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml"><img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6" alt="Windows 10/11">
  <img src="https://img.shields.io/github/license/mimaxon1/pc-remote" alt="License">
  <img src="https://img.shields.io/github/v/release/mimaxon1/pc-remote" alt="Latest release">
</p>

PC Remote 2.0 is a lightweight, open-source Windows and macOS remote that turns any Android or iPhone browser into a local control panel for your computer. Its Rust desktop app rests in the system tray or macOS menu bar, without background polling while idle.

Use it from the couch, beside a TV, during a presentation, or anywhere else on the same Wi-Fi/LAN.

## Why PC Remote?

- **No phone app required** — open the controller in any modern browser.
- **No account or cloud service** — traffic stays on your local network.
- **Fast pairing** — run PC Remote and scan the QR code.
- **Ready-made desktop builds** — no Python or mobile app is required for normal use.
- **Useful everyday controls** — apps, windows, volume, media, and available power actions.
- **Open source** — inspect it, modify it, or self-host it on your own PC.

If you are looking for an open-source, browser-based Windows or Mac remote, PC Remote is built for that use case.

On macOS, media controls target the Music app. Power and window actions use macOS Automation; window actions may also require PC Remote to be enabled under **System Settings → Privacy & Security → Accessibility**. On macOS 13 and later, if start-at-login registration needs approval, PC Remote opens **System Settings → General → Login Items**.

## Quick start

1. Open the [latest release](https://github.com/mimaxon1/pc-remote/releases/latest).
2. Download the installer or portable build for Windows, or the universal macOS app.
3. Run `PC Remote`.
4. Open **Show phone pairing QR code** from the system tray or menu bar.
5. Scan the QR code using a phone connected to the same local network.
6. Start controlling the PC from the browser.

Each 2.0 tagged release publishes a Windows installer, Windows portable ZIP, universal macOS app in a DMG and ZIP, and SHA-256 checksums.

## What you can control

- System volume and mute
- Media playback controls
- Current audio-output status
- Recent and pinned applications
- Launching desktop applications
- Opening, minimizing, and closing application windows
- Windows shutdown/restart and macOS power actions
- Autostart and tray behavior
- Light and dark themes
- Russian and English web UI

## Good fit for

- Couch / HTPC control
- Media PCs connected to a TV
- Presentation and demo PCs
- Local gaming or streaming setups
- A second-screen control panel
- Home-lab and self-hosted setups

## Local-first by design

```text
Phone browser
     |
     | local Wi-Fi / LAN
     v
Single Rust application
     +-- web controller :8080
     +-- control API :8000
     |
     +-- audio / media
     +-- app and window control
     +-- power actions
     +-- authentication
     |
Windows tray or macOS menu-bar icon
```

PC Remote does not require an external account or cloud backend.

## Security model

PC Remote is intended for a trusted local network. Do **not** expose its ports directly to the public internet.

- PINs are stored as salted PBKDF2-HMAC-SHA256 hashes
- Session tokens come from the operating system's secure random source and stay in memory
- CORS is restricted to local origins
- Login attempts are rate-limited
- Runtime settings are stored under `%APPDATA%\PC Remote` on Windows or `~/Library/Application Support/PC Remote` on macOS

The default transport is HTTP because the application targets local LAN use. For access from outside your home network, use an authenticated VPN or another appropriately secured transport instead of direct port forwarding.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Downloads and release builds

Windows releases:

- **Installer** — per-user Windows installation with a Start Menu shortcut.
- **Portable ZIP** — extract and run without installation.

macOS releases are universal apps for Apple Silicon and Intel, in DMG and ZIP formats. The app is ad-hoc signed but is not notarized yet, so macOS may require an explicit first-open approval.

Tagged releases (`v*`) build both platforms in GitHub Actions, run the Rust test suite, create the installers and archives, and publish SHA-256 checksums.

## Run from source

Requirements:

- Windows 10/11 or macOS 12+
- Rust stable
- PC and phone connected to the same local network

```sh
cargo run
```

## Build from source

```sh
cargo build --release
```

Portable output:

```text
target\release\pc-remote.exe
```

The Windows installer is built from [`installer/PC-Remote.iss`](installer/PC-Remote.iss) with Inno Setup 6.

## Testing

```powershell
cargo test --locked
```

Tests also run in GitHub Actions.

## Project layout

```text
.
|- src/                    Rust API, tray, authentication, and system controls
|- web/                    Phone web controller
|- Cargo.toml              Rust dependencies and build profile
|- Cargo.lock              Locked release dependencies
|- installer/              Windows installer definition
|- docs/                   Documentation and launch material
```

## Documentation

- [FAQ and use-case guide](docs/faq.md) · [Русский](docs/faq_RU.md)
- [Testing guide](docs/testing.md) · [Русский](docs/testing_RU.md)
- [Launch / promotion kit](docs/PROMOTION.md)
- [Changelog](CHANGELOG.md) · [Русский](CHANGELOG_RU.md)
- [Contributing](CONTRIBUTING.md)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
