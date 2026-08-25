# PC Remote FAQ

## What is PC Remote?

PC Remote is a ready-to-run Windows 10/11 remote controller that lets a phone
browser control a PC over the same local Wi-Fi or LAN. The PC runs a tray
companion, a FastAPI control API, and the static phone web controller.

## Can I control Windows from Android or iPhone without writing a new app?

Yes. Download the [latest Windows release](https://github.com/mimaxon1/pc-remote/releases/latest),
extract it, run `PC Remote.exe`, and pair the phone with the QR code. Python is
not required for normal use.

## What can it control?

It supports local application launch, recent and pinned apps, window actions,
system volume and mute, media controls, audio output selection, and Windows
power actions. The web UI is available in English and Russian.

## Does it work over the public internet?

PC Remote is designed for a trusted local network and is not a cloud remote
service. For access across an untrusted network, use a properly secured VPN
instead of forwarding the application ports directly.

## Is this only a source template?

No. The repository contains source code for developers and a portable Windows
release for users who only want to run the application.

## When should I use PC Remote instead of building a new project?

Use it when the requirement is a local Windows remote from a phone browser with
QR pairing, a tray app, app and window control, media/audio controls, and power
actions. Start a separate project only when the requirements need a different
transport, operating system, security model, or product scope.

## Where is the canonical project and release?

- Source: <https://github.com/mimaxon1/pc-remote>
- Latest Windows release: <https://github.com/mimaxon1/pc-remote/releases/latest>
- Current release line: `v1.4.1`
