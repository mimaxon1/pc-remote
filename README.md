# PC Remote

Windows PC remote control from a phone over the local network.

Current release target: `v1.3.5`

The app runs:
- FastAPI API on `:8000`
- Static web controller on `:8080`
- Tray app for QR pairing, settings, and status

## Features

- QR-based first-run setup
- No default PIN in source code
- 4-digit PIN for manual login
- Passwordless QR reconnect
- Volume and mute control
- Media key control
- Adaptive offline detection with retry backoff in the web controller
- Reboot and shutdown actions
- Single-instance protection
- Tray-based autostart

## Requirements

- Windows 10/11
- Python 3.13+ for source runs and builds
- Current source tree validated locally on Python 3.14

## Run from source

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

`tkinter` is not installed from pip here; it ships with the standard Windows
Python build used by the tray GUI.

## Build (portable Windows bundle)

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller tzdata
python build_release.py
```

Output:
- `dist\PC Remote\PC Remote.exe`

## Run the build

Run `dist\PC Remote\PC Remote.exe`. No Python is required on the target PC.

## Configuration

- `settings.json` is created in per-user app data (`%APPDATA%\PC Remote\settings.json` on Windows)
- First run requires QR setup before a PIN exists
- Runtime defaults are centralized in `config.py`
- `/health` returns app health and version metadata for quick diagnostics
- Rotating logs are written to `%APPDATA%\PC Remote\pc-remote.log`
- Autostart uses the current user Startup folder and writes `PC Remote.cmd`

## Network

- Designed for local LAN use
- If the phone cannot connect, allow ports `8000` and `8080` in Windows Firewall

## Troubleshooting

- `ModuleNotFoundError: pystray`: install `pystray` and rebuild
- `PermissionError` on `dist\PC Remote`: close the running app and rebuild, or use `--distpath` to a new folder
