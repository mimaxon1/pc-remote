# Changelog

## v1.3.5

- added adaptive offline retry/backoff polling in the web controller instead of fixed-interval retries during API outages
- exposed the app version and offline retry settings through runtime config and `/health`
- tightened local release hygiene by ignoring future `build*` and `dist*` artifact folders
- refreshed project docs and roadmap to match the post-`v1.3.4` codebase

## v1.3.4

- fixed the QR window label to show the full pairing URL with token instead of the bare web address
- reduced controller overhead by caching system info in the background and switching logs to incremental updates
- lazy-loaded tray, imaging, QR, and audio backend dependencies to improve packaged app startup time
- added a release build helper that clears persisted settings before packaging

## v1.3.3-preview

- added cached system info snapshots with TTL to reduce repeated expensive reads during polling
- kept system info responses isolated from callers by returning defensive copies
- added tests covering cache reuse, cache expiry, and copy safety

## v1.3.0

- fixed packaged (`.exe`) API startup in windowed mode by disabling uvicorn console logging config
- fixed packaged web server responses by suppressing `SimpleHTTPRequestHandler` stderr logging
- moved `settings.json` to per-user app data (`%APPDATA%\\PC Remote\\settings.json`) to keep release folder clean
- added migration from legacy `settings.json` location near script/exe
- updated network interfaces view in web UI to render one interface per line

## v1.1.0

- hardened first-run auth flow around QR setup
- blocked password change before initial QR setup is complete
- stopped silent fallback to default password on broken `settings.json`
- made QR tray window close only after pairing flow completes
- moved local tray-to-API calls to `127.0.0.1`
- removed `os.chdir()` from the web server thread
- improved rapid volume step handling on the web controller

## v1.0.0

- initial public build
