# PC-Android

Windows PC remote control from a phone over the local network.

The app runs:
- FastAPI API on `:8000`
- Static web controller on `:8080`
- Tray app for QR pairing, settings, and status

## Features

- QR-based first-run setup
- 4-digit password for manual login
- Passwordless QR reconnect
- Volume and mute control
- Media key control
- Reboot and shutdown actions
- Single-instance protection
- Tray-based autostart

## Requirements

- Windows 10/11
- Python 3.13+ for source runs and builds

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
python -m PyInstaller PC-Android.spec --clean -y
```

Output:
- `dist\PC-Android\PC-Android.exe`

## Run the build

Run `dist\PC-Android\PC-Android.exe`. No Python is required on the target PC.

## Configuration

- `settings.json` is created next to the script or built `.exe`
- Autostart uses the current user Startup folder and writes `PC-Android.cmd`

## Network

- Designed for local LAN use
- If the phone cannot connect, allow ports `8000` and `8080` in Windows Firewall

## Troubleshooting

- `ModuleNotFoundError: pystray`: install `pystray` and rebuild
- `PermissionError` on `dist\PC-Android`: close the running app and rebuild, or use `--distpath` to a new folder
