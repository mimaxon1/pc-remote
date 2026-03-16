# Roadmap

This roadmap reflects the public-facing direction of the project. It is shorter
and cleaner than the local working notes, but tracks the same priorities.

## Next Build Focus

The next build should ship one user-facing change only:

- Installable PWA support for the web controller

Scope for that build:

- Add a proper web app manifest
- Make the controller installable from supported mobile browsers
- Open in standalone app mode after installation
- Keep icons, app name, theme color, and launch entry consistent
- Replace the current legacy PWA cleanup workaround with a real install flow

Out of scope for that build:

- Full offline-first behavior
- Broad UI redesign
- New control features unrelated to installation
- Security and auth changes unless they directly block the PWA install flow

## Current Scope

PC Remote already provides:

- QR-based onboarding and PIN-backed login
- A FastAPI control API and lightweight browser controller
- Tray-based status, setup, and autostart handling
- Audio control, power actions, and recent / pinned app launch support
- A Windows-focused automated test suite

## Near-Term Priorities

### Security And Hardening

- Continue tightening auth edge cases around setup and password changes
- Document safer deployment guidance for users who want reverse proxies or HTTPS

### Reliability And UX

- Introduce stable API error codes so the web client no longer depends on response text
- Improve first-run diagnostics when pairing or local host detection goes wrong
- Keep source-run, packaged-run, and future PWA behavior aligned

### Controller Capabilities

- Refine quick app actions and window targeting for more edge cases
- Expand device and system controls only where they stay reliable on Windows
- Keep the web controller fast on low-power phones and unstable Wi-Fi

## Principles

- Local-network use comes first
- Reliability and maintainability beat feature count
- New features should come with tests and docs whenever practical
