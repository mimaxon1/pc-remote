# Changelog

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
