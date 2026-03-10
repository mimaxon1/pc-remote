"""PC controller (FastAPI + web UI + tray GUI).

Runs:
- API on :8000 (FastAPI/uvicorn)
- Web UI static server on :8080 (serves `web/`)
- Tray GUI for status/logs

Auth:
- On first run we create `settings.json` next to the exe/script (password is stored as a hash).
- UI logs in once (`/login`) and uses a short-lived token for the rest of the session.
"""
import threading
import gui
import uvicorn
import argparse
import ctypes
import functools
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from config import PASSWORD as DEFAULT_PASSWORD
import power, audio, apps
import media
import os
import socket
import sys
import time
from typing import Optional
from http.server import SimpleHTTPRequestHandler, HTTPServer
from fastapi.middleware.cors import CORSMiddleware
import psutil
import auth
import autostart
import net_utils
import single_instance

# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI()

# Password hash lives in settings.json next to the exe/script.
AUTH_INIT_ERROR: Optional[str] = None
try:
    AUTH = auth.AuthManager(default_password=DEFAULT_PASSWORD)
except auth.SettingsError as exc:
    AUTH = None
    AUTH_INIT_ERROR = str(exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Модели
# -----------------------------
class AuthModel(BaseModel):
    # Token-based auth is preferred. Password is only required for /login and
    # for legacy clients.
    token: Optional[str] = None
    password: Optional[str] = None

class VolumeModel(AuthModel):
    value: Optional[float] = None
    action: Optional[str] = None  # "up"/"down"

class MediaModel(AuthModel):
    action: str


class LogsModel(AuthModel):
    limit: int = 200


class LoginModel(BaseModel):
    password: str


class ChangePasswordModel(AuthModel):
    current_password: str
    new_password: str


class SetupPasswordModel(BaseModel):
    token: str
    new_password: str


class PairTokenModel(BaseModel):
    token: str


class AudioDeviceChangeModel(AuthModel):
    device_id: str


def _auth_manager() -> auth.AuthManager:
    if AUTH is None:
        raise HTTPException(
            status_code=500,
            detail="settings.json damaged; fix or delete it before continuing",
        )
    return AUTH


def _is_local_request(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in ("127.0.0.1", "::1")


def _battery_info() -> dict[str, object]:
    battery = psutil.sensors_battery()
    if battery is None:
        return {
            "present": False,
            "percent": None,
            "power_plugged": None,
            "secs_left": None,
        }
    secs_left = int(battery.secsleft) if battery.secsleft is not None and battery.secsleft >= 0 else None
    return {
        "present": True,
        "percent": float(battery.percent),
        "power_plugged": bool(battery.power_plugged),
        "secs_left": secs_left,
    }


def _system_info() -> dict[str, object]:
    cpu_percent = float(psutil.cpu_percent(interval=0.2))
    vm = psutil.virtual_memory()
    uptime_sec = int(time.time() - psutil.boot_time())
    current_ip = net_utils.get_local_ip()
    interfaces = net_utils.list_active_ipv4_interfaces()
    primary_interface = next((item for item in interfaces if item["ip"] == current_ip), None)
    return {
        "cpu_percent": cpu_percent,
        "ram_percent": float(vm.percent),
        "ram_used_mb": int(vm.used / (1024 * 1024)),
        "ram_total_mb": int(vm.total / (1024 * 1024)),
        "uptime_sec": uptime_sec,
        "battery": _battery_info(),
        "network": {
            "hostname": socket.gethostname(),
            "current_ip": current_ip,
            "primary_interface": primary_interface,
            "interfaces": interfaces,
        },
        "audio": {
            "active_output_device": audio.get_default_output_device(),
        },
    }

# -----------------------------
# Проверка пароля
# -----------------------------
def check(token: Optional[str], password: Optional[str]) -> None:
    """Authorize a request using either a token or a password (legacy)."""
    manager = _auth_manager()
    if manager.requires_password_setup():
        raise HTTPException(status_code=409, detail="Password setup required")
    if token and manager.verify_token(token):
        return
    if password and manager.verify_password(password):
        return
    raise HTTPException(status_code=403, detail="Invalid password or expired session")
# -----------------------------
# Эндпоинты
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/auth_state")
def auth_state():
    return {"requires_password_setup": _auth_manager().requires_password_setup()}
@app.post("/connect")
def connect_phone(data: AuthModel):
    """Mark phone as connected (tray status + log)."""
    check(data.token, data.password)
    gui.set_phone_status(True)
    gui.add_log("Телефон подключен")
    return {"status": "connected"}

@app.post("/disconnect")
def disconnect_phone(data: AuthModel):
    """Mark phone as disconnected (tray status + log)."""
    check(data.token, data.password)
    gui.set_phone_status(False)
    gui.add_log("Телефон отключен")
    return {"status": "disconnected"}


@app.post("/login")
def login(data: LoginModel):
    """Login with password once and get a short-lived token."""
    manager = _auth_manager()
    if manager.requires_password_setup():
        raise HTTPException(status_code=409, detail="Password setup is not complete yet")
    if not manager.verify_password(data.password):
        raise HTTPException(status_code=403, detail="Invalid password")
    token, expires_in = manager.issue_token()
    gui.add_log("Login: ok")
    return {"token": token, "expires_in": expires_in}

@app.post("/logout")
def logout(data: AuthModel):
    """Invalidate the current token (best-effort)."""
    manager = _auth_manager()
    if data.token:
        manager.tokens.revoke(data.token)
    return {"status": "bye"}

@app.post("/change_password")
def change_password(request: Request, data: ChangePasswordModel):
    """Change password (writes settings.json next to exe/script).

    Requires the current password. Remote clients must also have a valid session.
    """
    manager = _auth_manager()
    if manager.requires_password_setup():
        raise HTTPException(status_code=409, detail="Complete first-run setup via QR first")
    if not manager.verify_password(data.current_password):
        raise HTTPException(status_code=403, detail="Invalid current password")
    if data.token:
        if not manager.verify_token(data.token):
            raise HTTPException(status_code=403, detail="Invalid session")
    elif not _is_local_request(request):
        raise HTTPException(status_code=403, detail="Active session required")

    new_pw = data.new_password.strip()
    if len(new_pw) != 4 or not new_pw.isdigit():
        raise HTTPException(status_code=400, detail="New password must be exactly 4 digits")

    manager.change_password(new_pw)
    gui.add_log("Password changed")
    return {"status": "ok"}

@app.post("/setup_password")
def setup_password(data: SetupPasswordModel):
    """Complete first-run setup and issue a fresh session token."""
    manager = _auth_manager()
    if not manager.requires_password_setup():
        raise HTTPException(status_code=400, detail="Password setup is already complete")
    if not manager.verify_token(data.token):
        raise HTTPException(status_code=403, detail="Invalid QR token")

    new_pw = data.new_password.strip()
    if len(new_pw) != 4 or not new_pw.isdigit():
        raise HTTPException(status_code=400, detail="Password must be exactly 4 digits")

    token, expires_in = manager.setup_password(new_pw)
    manager.mark_pair_completed(data.token)
    gui.add_log("Password setup completed")
    return {"status": "ok", "token": token, "expires_in": expires_in}

@app.post("/pair")
def pair_token(request: Request):
    """Issue a short-lived token for QR login (local only)."""
    manager = _auth_manager()
    if not _is_local_request(request):
        raise HTTPException(status_code=403, detail="Local only")
    token, expires_in = manager.issue_pair_token()
    gui.add_log("QR pairing token issued")
    return {
        "token": token,
        "expires_in": expires_in,
        "requires_password_setup": manager.requires_password_setup(),
    }

@app.post("/pair_touch")
def pair_touch(data: PairTokenModel):
    """Mark QR token as opened on another device."""
    if not _auth_manager().mark_pair_touched(data.token):
        raise HTTPException(status_code=403, detail="Invalid QR token")
    return {"status": "ok"}


@app.post("/pair_complete")
def pair_complete(data: PairTokenModel):
    """Mark QR flow as completed successfully."""
    if not _auth_manager().mark_pair_completed(data.token):
        raise HTTPException(status_code=403, detail="Invalid QR token")
    return {"status": "ok"}

@app.post("/pair_status")
def pair_status(request: Request, data: PairTokenModel):
    """Return the current QR token state."""
    manager = _auth_manager()
    if not _is_local_request(request):
        raise HTTPException(status_code=403, detail="Local only")
    opened, completed = manager.get_pair_status(data.token)
    return {"opened": opened, "completed": completed}

@app.post("/volume")
def volume(data: VolumeModel):
    """Set volume (data.value) or step volume (data.action up/down)."""
    check(data.token, data.password)
    if data.value is not None:
        audio.set_volume(data.value)
        gui.add_log(f"Громкость установлена: {data.value}")
    elif data.action in ("up", "down"):
        current = audio.get_volume()
        step = 0.05
        new_value = current + step if data.action == "up" else current - step
        audio.set_volume(new_value)
        gui.add_log(f"Громкость {data.action}")
    return {
        "volume": audio.get_volume(),
        "muted": audio.is_muted(),
    }

@app.post("/mute")
def mute(data: AuthModel):
    """Toggle mute and return the new state."""
    check(data.token, data.password)
    state = audio.toggle_mute()
    gui.add_log(f"Mute: {state}")
    return {"muted": state}

@app.post("/media")
def media_action(data: MediaModel):
    """Send media key action (play_pause/next/prev/stop)."""
    check(data.token, data.password)
    try:
        media.send(data.action)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown action")
    except Exception:
        raise HTTPException(status_code=500, detail="Media error")
    gui.add_log(f"Media: {data.action}")
    return {"status": "ok"}

@app.post("/status")
def status(data: AuthModel):
    """Return current volume + mute state."""
    check(data.token, data.password)
    return {
        "volume": audio.get_volume(),   # scalar 0.0-1.0 via pycaw
        "muted": audio.is_muted()
    }


@app.post("/stats")
def stats(data: AuthModel):
    """Basic system stats for the web UI (CPU/RAM/Uptime)."""
    check(data.token, data.password)
    info = _system_info()
    return {
        "cpu_percent": info["cpu_percent"],
        "ram_percent": info["ram_percent"],
        "ram_used_mb": info["ram_used_mb"],
        "ram_total_mb": info["ram_total_mb"],
        "uptime_sec": info["uptime_sec"],
    }


@app.post("/info")
def info(data: AuthModel):
    """Detailed system info for the Info tab."""
    check(data.token, data.password)
    return _system_info()


@app.post("/audio/devices")
def audio_devices(data: AuthModel):
    """Return available output devices."""
    check(data.token, data.password)
    return {
        "devices": audio.list_output_devices(),
        "active_output_device": audio.get_default_output_device(),
    }


@app.post("/audio/device")
def audio_device(data: AudioDeviceChangeModel):
    """Switch the active default output device."""
    check(data.token, data.password)
    try:
        current = audio.set_default_output_device(data.device_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    gui.add_log(f"Output device: {current['name']}")
    return {
        "status": "ok",
        "active_output_device": current,
        "devices": audio.list_output_devices(),
    }


@app.post("/logs")
def logs(data: LogsModel):
    """Return recent logs (last N lines)."""
    check(data.token, data.password)
    limit = max(1, min(1000, int(data.limit)))
    items = list(gui.logs[-limit:])
    return {"logs": items}

@app.post("/shutdown")
def shutdown(data: AuthModel):
    """Shutdown the PC."""
    check(data.token, data.password)
    power.shutdown()
    gui.add_log("ПК выключен")
    return {"status": "bye"}


@app.post("/reboot")
def reboot(data: AuthModel):
    """Reboot the PC."""
    check(data.token, data.password)
    power.reboot()
    gui.add_log("ПК перезагружен")
    return {"status": "rebooting"}

# -----------------------------
# Веб-сервер для index.html
# -----------------------------
def run_web():
    """Serve the `web/` folder via a simple HTTP server on port 8080."""
    if getattr(sys, "frozen", False):
        # PyInstaller:
        # - onefile: data is extracted to sys._MEIPASS
        # - onedir: data may live under "_internal"
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            getattr(sys, "_MEIPASS", None),
            os.path.join(exe_dir, "_internal"),
            exe_dir,
        ]
    else:
        candidates = [os.path.dirname(os.path.abspath(__file__))]

    web_dir = None
    for base in candidates:
        if not base:
            continue
        candidate = os.path.join(base, "web")
        if os.path.isdir(candidate):
            web_dir = candidate
            break

    if not web_dir:
        raise RuntimeError("web folder not found (checked: %s)" % candidates)

    ip = net_utils.get_local_ip()
    port = 8080

    handler = functools.partial(SimpleHTTPRequestHandler, directory=web_dir)
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"Web controller available at http://{ip}:{port}")
    gui.add_log(f"Web controller: http://{ip}:{port}")
    gui.add_log(f"API: http://{ip}:8000")

    server.serve_forever()

# -----------------------------
# Запуск API
# -----------------------------
def run_api():
    """Run the FastAPI app via uvicorn on port 8000."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


def hide_console_after_startup(delay: float = 2.0) -> None:
    """Hide the Windows console shortly after startup in packaged builds."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    def worker() -> None:
        time.sleep(delay)
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()

def handle_cli() -> bool:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--install-autostart", action="store_true")
    parser.add_argument("--remove-autostart", action="store_true")
    parser.add_argument("--autostart-status", action="store_true")
    args, _ = parser.parse_known_args()

    if args.install_autostart:
        path = autostart.install()
        print(f"Autostart enabled: {path}")
        return True
    if args.remove_autostart:
        removed = autostart.remove()
        print("Autostart disabled" if removed else "Autostart was not enabled")
        return True
    if args.autostart_status:
        print("enabled" if autostart.is_enabled() else "disabled")
        return True
    return False

if __name__ == "__main__":
    if handle_cli():
        sys.exit(0)
    if not single_instance.acquire():
        sys.exit(0)
    print("Ассистент запущен!")
    if AUTH_INIT_ERROR:
        gui.add_log(f"settings.json error: {AUTH_INIT_ERROR}")
    threading.Thread(target=run_api, daemon=True).start()
    threading.Thread(target=run_web, daemon=True).start()
    hide_console_after_startup()
    gui.run()
