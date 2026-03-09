# PC-Android

Windows PC remote control from a phone over the local network.

The app starts:
- FastAPI API on `:8000`
- static web controller on `:8080`
- tray app for QR pairing, settings, and status

## Main features

- QR-based first-run setup
- 4-digit password for manual login
- passwordless QR reconnect
- volume and mute control
- media key control
- reboot and shutdown actions
- single-instance protection
- tray-based autostart

## Requirements

- Windows 10/11
- Python 3.13 for source runs

## Run from source

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Build

```powershell
python -m PyInstaller PC-Android.spec --clean
```

## Notes

- `settings.json` is created next to the script or built `.exe`
- `PLAN.md` is intentionally local-only and ignored by git
- the project is designed for local LAN use
