# Roadmap

This roadmap reflects the public-facing direction of the project. It is shorter
and cleaner than the local working notes, but tracks the same priorities.

## Current Scope

PC Remote already provides:

- QR-based onboarding and PIN-backed login
- A FastAPI control API and lightweight browser controller
- Tray-based status, setup, and autostart handling
- Audio control, power actions, and recent / pinned app launch support
- A Windows-focused automated test suite

## Near-Term Priorities

### Security And Hardening

- Add explicit login rate limiting and lockout telemetry
- Continue tightening auth edge cases around setup and password changes
- Document safer deployment guidance for users who want reverse proxies or HTTPS

### Reliability And UX

- Keep startup and shutdown behavior predictable across source and packaged runs
- Improve first-run diagnostics when pairing or local host detection goes wrong
- Make offline / reconnect messaging in the web controller even clearer

### Controller Capabilities

- Refine quick app actions and window targeting for more edge cases
- Expand device and system controls only where they stay reliable on Windows
- Keep the web controller fast on low-power phones and unstable Wi-Fi

## Principles

- Local-network use comes first
- Reliability and maintainability beat feature count
- New features should come with tests and docs whenever practical
