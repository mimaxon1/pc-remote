"""Centralized application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


APP_NAME = "PC Remote"
LOGGER_NAME = APP_NAME
SETTINGS_FILENAME = "settings.json"
LOG_FILE_NAME = "pc-remote.log"
LEGACY_APP_NAMES = ("PC-Android",)

PIN_LENGTH = 4
PIN_PATTERN = r"^\d{4}$"
PIN_PLACEHOLDER = "•" * PIN_LENGTH

API_HOST = "0.0.0.0"
API_PORT = _env_int("PC_REMOTE_API_PORT", 8000)
WEB_HOST = "0.0.0.0"
WEB_PORT = _env_int("PC_REMOTE_WEB_PORT", 8080)

TOKEN_TTL_SECONDS = _env_int("PC_REMOTE_TOKEN_TTL", 3600)
HTTP_CLIENT_TIMEOUT_SECONDS = _env_float("PC_REMOTE_HTTP_TIMEOUT", 5.0)
CONSOLE_HIDE_DELAY_SECONDS = _env_float("PC_REMOTE_HIDE_CONSOLE_DELAY", 2.0)

LOG_BUFFER_LIMIT = _env_int("PC_REMOTE_LOG_BUFFER_LIMIT", 500)
DEFAULT_LOG_LIMIT = _env_int("PC_REMOTE_DEFAULT_LOG_LIMIT", 200)
MAX_LOG_LIMIT = _env_int("PC_REMOTE_MAX_LOG_LIMIT", 1000)
LOG_FILE_MAX_BYTES = _env_int("PC_REMOTE_LOG_FILE_MAX_BYTES", 1048576)
LOG_FILE_BACKUP_COUNT = _env_int("PC_REMOTE_LOG_FILE_BACKUPS", 3)

WEB_STATUS_POLL_MS = _env_int("PC_REMOTE_WEB_STATUS_POLL_MS", 4000)
PAIR_STATUS_POLL_MS = _env_int("PC_REMOTE_PAIR_STATUS_POLL_MS", 700)
TK_QUEUE_POLL_MS = _env_int("PC_REMOTE_TK_QUEUE_POLL_MS", 80)
SYSTEM_INFO_CACHE_TTL_SECONDS = _env_float("PC_REMOTE_SYSTEM_INFO_CACHE_TTL", 1.0)

VOLUME_STEP = _env_float("PC_REMOTE_VOLUME_STEP", 0.05)
LOGIN_ATTEMPT_LIMIT = _env_int("PC_REMOTE_LOGIN_ATTEMPT_LIMIT", 5)
LOGIN_ATTEMPT_WINDOW_SECONDS = _env_int("PC_REMOTE_LOGIN_ATTEMPT_WINDOW_SECONDS", 60)
LOGIN_BLOCK_SECONDS = _env_int("PC_REMOTE_LOGIN_BLOCK_SECONDS", 900)

MIN_TOKEN_LENGTH = 32
MAX_TOKEN_LENGTH = 256
MAX_DEVICE_ID_LENGTH = 512


def appdata_base_dir() -> Optional[Path]:
    if os.name != "nt":
        return None
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    return Path(base) if base else None


def app_dir() -> Path:
    base = appdata_base_dir()
    if base:
        return base / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME
