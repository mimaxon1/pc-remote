# Privacy Policy

Last updated: September 7, 2026

PC Remote is a local-first, open-source application for controlling a Windows PC from a phone or other browser on the same local network.

## Data handling

PC Remote does not require an account and does not intentionally send telemetry, analytics, control commands, pairing data, or personal information to developer-operated servers.

Normal control traffic is exchanged directly between the Windows PC running PC Remote and the browser used as the remote controller over the local network.

## Data stored on the PC

PC Remote stores runtime settings and authentication-related data locally on the Windows PC. This can include application preferences, pairing/authentication state, and security values needed to operate the local controller. Runtime settings are stored under `%APPDATA%\PC Remote`.

PINs are stored as salted PBKDF2-HMAC-SHA256 hashes. Session tokens are generated locally and kept in memory.

## Network access

PC Remote runs local HTTP services so devices on the same LAN can connect to the controller. The application is intended for trusted local networks and should not be exposed directly to the public internet.

If remote access from outside the local network is required, use an appropriately secured VPN rather than direct port forwarding.

## Third-party services

PC Remote does not require a developer-operated cloud backend or third-party analytics service for its core functionality.

Links to GitHub in the application documentation or project pages are governed by GitHub's own privacy practices when opened by the user.

## Source code and questions

The source code is available at:
https://github.com/mimaxon1/pc-remote

Privacy or security questions can be reported through the project's GitHub issue tracker or the process described in `SECURITY.md`.
