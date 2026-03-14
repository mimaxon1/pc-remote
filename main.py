"""PC controller (FastAPI + web UI + tray GUI)."""
import argparse
import ctypes
import functools
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Annotated, Callable, Literal, Optional
from urllib.parse import urlsplit

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

import apps
import audio
import auth
import autostart
import config
import gui
import logging_utils
import media
import net_utils
import power
import single_instance

logger = logging_utils.setup_logging()

# Global server references for graceful shutdown
_api_server: Optional[uvicorn.Server] = None
_web_server: Optional[HTTPServer] = None

# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI()

# PIN hash lives in per-user app data.
AUTH: Optional[auth.AuthManager] = None
AUTH_INIT_ERROR: Optional[str] = None
_AUTH_INIT_ATTEMPTED = False


def _ensure_auth_manager_initialized() -> None:
    global AUTH, AUTH_INIT_ERROR, _AUTH_INIT_ATTEMPTED
    if _AUTH_INIT_ATTEMPTED:
        return
    _AUTH_INIT_ATTEMPTED = True
    try:
        AUTH = auth.AuthManager()
        AUTH_INIT_ERROR = None
    except auth.SettingsError as exc:
        AUTH = None
        AUTH_INIT_ERROR = str(exc)


allowed_origins = [
    f"http://localhost:{config.WEB_PORT}",
    f"http://127.0.0.1:{config.WEB_PORT}",
    f"http://localhost:{config.API_PORT}",
    f"http://127.0.0.1:{config.API_PORT}",
]
try:
    local_ip = net_utils.get_local_ip()
    allowed_origins.append(f"http://{local_ip}:{config.WEB_PORT}")
    allowed_origins.append(f"http://{local_ip}:{config.API_PORT}")
except Exception as exc:
    logger.warning("Failed to determine local IP for CORS allowlist: %s", exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)

# -----------------------------
# Модели
# -----------------------------
PinStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=config.PIN_LENGTH,
        max_length=config.PIN_LENGTH,
        pattern=config.PIN_PATTERN,
    ),
]
TokenStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=config.MIN_TOKEN_LENGTH,
        max_length=config.MAX_TOKEN_LENGTH,
    ),
]
DeviceIdStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=config.MAX_DEVICE_ID_LENGTH,
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthModel(StrictModel):
    token: Optional[TokenStr] = None
    password: Optional[PinStr] = None


class VolumeModel(AuthModel):
    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    action: Optional[Literal["up", "down"]] = None

    @model_validator(mode="after")
    def validate_volume_request(self) -> "VolumeModel":
        if (self.value is None) == (self.action is None):
            raise ValueError("Provide either value or action")
        return self


class MediaModel(AuthModel):
    action: Literal["play_pause", "next", "prev", "stop"]


class LogsModel(AuthModel):
    limit: int = Field(default=config.DEFAULT_LOG_LIMIT, ge=1, le=config.MAX_LOG_LIMIT)
    since: Optional[int] = Field(default=None, ge=0)


class LoginModel(StrictModel):
    password: PinStr


class ChangePasswordModel(AuthModel):
    current_password: PinStr
    new_password: PinStr


class SetupPasswordModel(StrictModel):
    token: TokenStr
    new_password: PinStr


class PairTokenModel(StrictModel):
    token: TokenStr


class AudioDeviceChangeModel(AuthModel):
    device_id: DeviceIdStr


@dataclass
class LoginAttemptState:
    attempts: list[float] = field(default_factory=list)
    blocked_until: float = 0.0


class LoginRateLimiter:
    def __init__(
        self,
        max_attempts: int = config.LOGIN_ATTEMPT_LIMIT,
        window_seconds: int = config.LOGIN_ATTEMPT_WINDOW_SECONDS,
        block_seconds: int = config.LOGIN_BLOCK_SECONDS,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._window_seconds = max(1, int(window_seconds))
        self._block_seconds = max(1, int(block_seconds))
        self._now_fn = now_fn
        self._lock = threading.Lock()
        self._state: dict[str, LoginAttemptState] = {}

    def _prune_locked(self, client_ip: str, now: float) -> LoginAttemptState | None:
        entry = self._state.get(client_ip)
        if entry is None:
            return None

        attempts = [ts for ts in entry.attempts if now - ts < self._window_seconds]
        blocked_until = entry.blocked_until
        if blocked_until <= now:
            blocked_until = 0.0

        if attempts or blocked_until:
            entry.attempts = attempts
            entry.blocked_until = blocked_until
            return entry

        self._state.pop(client_ip, None)
        return None

    def blocked_until(self, client_ip: str) -> float | None:
        now = float(self._now_fn())
        with self._lock:
            entry = self._prune_locked(client_ip, now)
            if entry is None:
                return None
            blocked_until = entry.blocked_until
            return blocked_until or None

    def record_failure(self, client_ip: str) -> float | None:
        now = float(self._now_fn())
        with self._lock:
            entry = self._prune_locked(client_ip, now)
            if entry is None:
                entry = LoginAttemptState()

            blocked_until = entry.blocked_until
            if blocked_until > now:
                self._state[client_ip] = entry
                return blocked_until

            attempts = list(entry.attempts)
            attempts.append(now)
            entry.attempts = attempts
            if len(attempts) > self._max_attempts:
                blocked_until = now + self._block_seconds
                entry.blocked_until = blocked_until
                self._state[client_ip] = entry
                return blocked_until

            entry.blocked_until = 0.0
            self._state[client_ip] = entry
            return None

    def reset(self, client_ip: str) -> None:
        with self._lock:
            self._state.pop(client_ip, None)


LOGIN_RATE_LIMITER = LoginRateLimiter()


def _auth_manager() -> auth.AuthManager:
    _ensure_auth_manager_initialized()
    if AUTH is None:
        raise HTTPException(
            status_code=500,
            detail="settings.json damaged; fix or delete it before continuing",
        )
    return AUTH


def _is_local_request(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in ("127.0.0.1", "::1")


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


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


@dataclass
class SystemInfoCacheEntry:
    value: dict[str, object] | None = None
    captured_at: float = 0.0


@dataclass
class SystemInfoState:
    runtime: SystemInfoCacheEntry = field(default_factory=SystemInfoCacheEntry)
    battery: SystemInfoCacheEntry = field(default_factory=SystemInfoCacheEntry)
    network: SystemInfoCacheEntry = field(default_factory=SystemInfoCacheEntry)
    audio: SystemInfoCacheEntry = field(default_factory=SystemInfoCacheEntry)


_SYSTEM_INFO_LOCK = threading.Lock()
_SYSTEM_INFO_STATE = SystemInfoState()
_SYSTEM_INFO_THREAD: threading.Thread | None = None
_SYSTEM_INFO_STOP_EVENT = threading.Event()
_SYSTEM_BOOT_TIME = psutil.boot_time()


def _clone_interface_info(value: object) -> object:
    return dict(value) if isinstance(value, dict) else value


def _clone_system_info_payload(
    runtime: dict[str, object] | None,
    battery: dict[str, object] | None,
    network: dict[str, object] | None,
    audio_info: dict[str, object] | None,
) -> dict[str, object]:
    runtime_data = dict(runtime) if isinstance(runtime, dict) else {}
    battery_data = dict(battery) if isinstance(battery, dict) else {}
    network_data = network if isinstance(network, dict) else {}
    audio_data = dict(audio_info) if isinstance(audio_info, dict) else {}
    interfaces = network_data.get("interfaces", [])
    return {
        "cpu_percent": runtime_data.get("cpu_percent"),
        "ram_percent": runtime_data.get("ram_percent"),
        "ram_used_mb": runtime_data.get("ram_used_mb"),
        "ram_total_mb": runtime_data.get("ram_total_mb"),
        "uptime_sec": int(max(0.0, time.time() - _SYSTEM_BOOT_TIME)),
        "battery": battery_data,
        "network": {
            "hostname": network_data.get("hostname"),
            "current_ip": network_data.get("current_ip"),
            "primary_interface": _clone_interface_info(network_data.get("primary_interface")),
            "interfaces": [_clone_interface_info(item) for item in interfaces] if isinstance(interfaces, list) else [],
        },
        "audio": {
            "active_output_device": _clone_interface_info(audio_data.get("active_output_device")),
        },
    }


def _collect_runtime_info(cpu_interval: float = 0.0) -> dict[str, object]:
    vm = psutil.virtual_memory()
    return {
        "cpu_percent": float(psutil.cpu_percent(interval=cpu_interval)),
        "ram_percent": float(vm.percent),
        "ram_used_mb": int(vm.used / (1024 * 1024)),
        "ram_total_mb": int(vm.total / (1024 * 1024)),
    }


def _collect_network_info() -> dict[str, object]:
    current_ip = net_utils.get_local_ip()
    interfaces = net_utils.list_active_ipv4_interfaces()
    primary_interface = next((item for item in interfaces if item["ip"] == current_ip), None)
    return {
        "hostname": socket.gethostname(),
        "current_ip": current_ip,
        "primary_interface": primary_interface,
        "interfaces": interfaces,
    }


def _collect_audio_info() -> dict[str, object]:
    return {
        "active_output_device": audio.get_default_output_device(),
    }


def _system_info_entry_is_fresh(entry: SystemInfoCacheEntry, ttl: float, now: float) -> bool:
    return entry.value is not None and now - entry.captured_at < ttl


def _refresh_system_info_cache(force: bool = False, allow_blocking: bool = False) -> None:
    now = time.time()
    runtime_ttl = max(0.0, float(config.SYSTEM_INFO_RUNTIME_TTL_SECONDS))
    battery_ttl = max(0.0, float(config.SYSTEM_INFO_BATTERY_TTL_SECONDS))
    network_ttl = max(0.0, float(config.SYSTEM_INFO_NETWORK_TTL_SECONDS))
    audio_ttl = max(0.0, float(config.SYSTEM_INFO_AUDIO_TTL_SECONDS))

    with _SYSTEM_INFO_LOCK:
        need_runtime = force or not _system_info_entry_is_fresh(_SYSTEM_INFO_STATE.runtime, runtime_ttl, now)
        need_battery = force or not _system_info_entry_is_fresh(_SYSTEM_INFO_STATE.battery, battery_ttl, now)
        need_network = force or not _system_info_entry_is_fresh(_SYSTEM_INFO_STATE.network, network_ttl, now)
        need_audio = force or not _system_info_entry_is_fresh(_SYSTEM_INFO_STATE.audio, audio_ttl, now)

    updates: dict[str, dict[str, object]] = {}
    if need_runtime:
        try:
            interval = 0.2 if allow_blocking else 0.0
            updates["runtime"] = _collect_runtime_info(cpu_interval=interval)
        except Exception as exc:
            logger.warning("Failed to refresh runtime system info: %s", exc)
    if need_battery:
        try:
            updates["battery"] = _battery_info()
        except Exception as exc:
            logger.warning("Failed to refresh battery info: %s", exc)
    if need_network:
        try:
            updates["network"] = _collect_network_info()
        except Exception as exc:
            logger.warning("Failed to refresh network info: %s", exc)
    if need_audio:
        try:
            updates["audio"] = _collect_audio_info()
        except Exception as exc:
            logger.warning("Failed to refresh audio info: %s", exc)

    if not updates:
        return

    captured_at = time.time()
    with _SYSTEM_INFO_LOCK:
        for key, value in updates.items():
            setattr(_SYSTEM_INFO_STATE, key, SystemInfoCacheEntry(value=value, captured_at=captured_at))


def _system_info_sampler_loop() -> None:
    interval = max(0.2, float(config.SYSTEM_INFO_SAMPLE_INTERVAL_SECONDS))
    while not _SYSTEM_INFO_STOP_EVENT.wait(interval):
        _refresh_system_info_cache(force=False, allow_blocking=True)


def start_system_info_sampler() -> None:
    global _SYSTEM_INFO_THREAD
    if _SYSTEM_INFO_THREAD is not None and _SYSTEM_INFO_THREAD.is_alive():
        return
    _SYSTEM_INFO_STOP_EVENT.clear()
    _refresh_system_info_cache(force=True, allow_blocking=True)
    _SYSTEM_INFO_THREAD = threading.Thread(
        target=_system_info_sampler_loop,
        name="SystemInfo-Sampler",
        daemon=True,
    )
    _SYSTEM_INFO_THREAD.start()


def stop_system_info_sampler() -> None:
    global _SYSTEM_INFO_THREAD
    _SYSTEM_INFO_STOP_EVENT.set()
    thread = _SYSTEM_INFO_THREAD
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=1.0)
    _SYSTEM_INFO_THREAD = None


def _system_info() -> dict[str, object]:
    with _SYSTEM_INFO_LOCK:
        runtime_missing = _SYSTEM_INFO_STATE.runtime.value is None
    _refresh_system_info_cache(force=False, allow_blocking=runtime_missing)
    with _SYSTEM_INFO_LOCK:
        runtime = _SYSTEM_INFO_STATE.runtime.value
        battery = _SYSTEM_INFO_STATE.battery.value
        network = _SYSTEM_INFO_STATE.network.value
        audio_info = _SYSTEM_INFO_STATE.audio.value
    return _clone_system_info_payload(runtime, battery, network, audio_info)

# -----------------------------
# Проверка PIN
# -----------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def check(token: Optional[str], password: Optional[str]) -> None:
    """Authorize a request using either a session token or a PIN."""
    manager = _auth_manager()
    if manager.requires_password_setup():
        raise HTTPException(status_code=409, detail="PIN setup required")
    if token and manager.verify_token(token):
        return
    if password and manager.verify_password(password):
        return
    raise HTTPException(status_code=403, detail="Invalid PIN or expired session")
# -----------------------------
# Эндпоинты
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    """Health check endpoint (no auth required) for load balancers and monitoring."""
    _ensure_auth_manager_initialized()
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "auth_ready": AUTH is not None and not AUTH.requires_password_setup(),
    }


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
def login(request: Request, data: LoginModel):
    """Login with a PIN once and get a short-lived session token."""
    manager = _auth_manager()
    client_ip = _client_ip(request)
    if manager.requires_password_setup():
        logger.warning("Login attempt before setup | IP: %s", client_ip)
        raise HTTPException(status_code=409, detail="PIN setup is not complete yet")
    if LOGIN_RATE_LIMITER.blocked_until(client_ip):
        logger.critical("Brute force login blocked | IP: %s", client_ip)
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    if not manager.verify_password(data.password):
        blocked_until = LOGIN_RATE_LIMITER.record_failure(client_ip)
        logger.warning("Login failed: invalid PIN | IP: %s", client_ip)
        if blocked_until:
            logger.critical("Brute force protection triggered | IP: %s", client_ip)
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        raise HTTPException(status_code=403, detail="Invalid PIN")
    LOGIN_RATE_LIMITER.reset(client_ip)
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
    """Change the PIN (writes settings.json in per-user app data).

    Requires the current PIN. Remote clients must also have a valid session.
    """
    manager = _auth_manager()
    if manager.requires_password_setup():
        raise HTTPException(status_code=409, detail="Complete first-run setup via QR first")
    if not manager.verify_password(data.current_password):
        raise HTTPException(status_code=403, detail="Invalid current PIN")
    if data.token:
        if not manager.verify_token(data.token):
            raise HTTPException(status_code=403, detail="Invalid session")
    elif not _is_local_request(request):
        raise HTTPException(status_code=403, detail="Active session required")

    manager.change_password(data.new_password)
    gui.add_log("PIN changed")
    return {"status": "ok"}

@app.post("/setup_password")
def setup_password(data: SetupPasswordModel):
    """Complete first-run PIN setup and issue a fresh session token."""
    manager = _auth_manager()
    if not manager.requires_password_setup():
        raise HTTPException(status_code=400, detail="PIN setup is already complete")
    if not manager.verify_token(data.token):
        raise HTTPException(status_code=403, detail="Invalid QR token")

    token, expires_in = manager.setup_password(data.new_password)
    manager.mark_pair_completed(data.token)
    gui.notify_pair_completed(data.token)
    gui.add_log("PIN setup completed")
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
    gui.notify_pair_completed(data.token)
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
    else:
        current = audio.get_volume()
        step = config.VOLUME_STEP
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
    except Exception as exc:
        logger.exception("Media action failed: %s", exc)
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
    items, next_since, reset = gui.get_logs(data.since, data.limit)
    return {
        "logs": [entry.message for entry in items],
        "next_since": next_since,
        "reset": reset,
    }

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
# Port checking
# -----------------------------
def check_port_available(port: int) -> bool:
    """Check whether we can bind the port for a server on all interfaces."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("0.0.0.0", port))
            return True
    except Exception:
        return False

def verify_ports_available(api_port: int = config.API_PORT, web_port: int = config.WEB_PORT) -> bool:
    """Verify both API and web ports are available. Logs errors and returns False if not."""
    errors = []
    if not check_port_available(api_port):
        errors.append(f"Port {api_port} (API) is already in use")
    if not check_port_available(web_port):
        errors.append(f"Port {web_port} (Web) is already in use")
    
    if errors:
        for err in errors:
            logger.error(err)
            gui.add_log(f"ERROR: {err}")
        return False
    return True


def _runtime_config_script() -> bytes:
    payload = {
        "appVersion": config.APP_VERSION,
        "apiPort": config.API_PORT,
        "webPort": config.WEB_PORT,
        "pinLength": config.PIN_LENGTH,
        "pollIntervalMs": config.WEB_STATUS_POLL_MS,
        "offlineRetryMinMs": config.WEB_OFFLINE_RETRY_MIN_MS,
        "offlineRetryMaxMs": config.WEB_OFFLINE_RETRY_MAX_MS,
        "pairPollIntervalMs": config.PAIR_STATUS_POLL_MS,
    }
    return f"window.__PC_REMOTE_CONFIG__ = Object.freeze({json.dumps(payload)});".encode("utf-8")

# -----------------------------
# Веб-сервер для index.html
# ────────────────────────────
def run_web():
    """Serve the `web/` folder via a simple HTTP server."""
    global _web_server
    
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
    port = config.WEB_PORT

    class _QuietStaticHandler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/runtime-config.js":
                body = _runtime_config_script()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            # In windowed builds sys.stderr can be None; suppress per-request stderr logging.
            return

    handler = functools.partial(_QuietStaticHandler, directory=web_dir)
    _web_server = HTTPServer((config.WEB_HOST, port), handler)
    logger.info(f"Web controller available at http://{ip}:{port}")
    gui.add_log(f"Web controller: http://{ip}:{port}")
    gui.add_log(f"API: http://{ip}:{config.API_PORT}")

    _web_server.serve_forever()

# Запуск API
# ──────────
def run_api():
    """Run the FastAPI app via uvicorn."""
    global _api_server
    logger.info("API starting on port %s", config.API_PORT)
    try:
        uvicorn_config = uvicorn.Config(
            app=app,
            host=config.API_HOST,
            port=config.API_PORT,
            loop="asyncio",
            http="h11",
            ws="none",
            log_config=None,
            access_log=False,
            use_colors=False,
            log_level="info",
        )
        _api_server = uvicorn.Server(uvicorn_config)
        _api_server.run()
    except KeyboardInterrupt:
        logger.info("API server interrupted")
    except Exception:
        logger.exception("API server error")
    finally:
        _api_server = None


def shutdown_servers():
    """Gracefully shutdown all servers."""
    global _api_server, _web_server
    logger.info("Shutting down servers...")
    stop_system_info_sampler()
    try:
        if _api_server is not None:
            _api_server.should_exit = True
            logger.info("API server stop requested")
    except Exception:
        logger.exception("Error shutting down API server")
    try:
        if _web_server:
            _web_server.shutdown()
            _web_server.server_close()
            logger.info("Web server stopped")
    except Exception:
        logger.exception("Error shutting down web server")
    finally:
        _web_server = None


def hide_console_after_startup(delay: float = config.CONSOLE_HIDE_DELAY_SECONDS) -> None:
    """Hide the Windows console shortly after startup in packaged builds."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    def worker() -> None:
        time.sleep(delay)
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception as exc:
            logger.warning("Failed to hide console window: %s", exc)

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
    import atexit
    
    if handle_cli():
        sys.exit(0)
    if not single_instance.acquire():
        sys.exit(0)

    logger.info("%s %s starting", config.APP_NAME, config.APP_VERSION)
    
    # Verify ports are available before starting servers
    if not verify_ports_available():
        logger.error("Cannot start: required ports are in use")
        gui.add_log(f"ERROR: Cannot start - ports {config.API_PORT}/{config.WEB_PORT} are in use")
        sys.exit(1)
    
    # Register graceful shutdown
    atexit.register(shutdown_servers)

    _ensure_auth_manager_initialized()
    if AUTH_INIT_ERROR:
        logger.error(f"settings.json error: {AUTH_INIT_ERROR}")
        gui.add_log(f"settings.json error: {AUTH_INIT_ERROR}")

    start_system_info_sampler()
    
    api_thread = threading.Thread(target=run_api, name="API-Server", daemon=True)
    web_thread = threading.Thread(target=run_web, name="Web-Server", daemon=True)
    api_thread.start()
    web_thread.start()
    
    hide_console_after_startup()
    try:
        gui.run()
    finally:
        logger.info("Main GUI closed, initiating shutdown...")
        shutdown_servers()
        web_thread.join(timeout=2)
        api_thread.join(timeout=2)
        sys.exit(0)
