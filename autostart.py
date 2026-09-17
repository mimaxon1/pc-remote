"""Autostart management for Windows (current user)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import config

logger = logging.getLogger(config.LOGGER_NAME)

AUTOSTART_FILENAME = f"{config.APP_NAME}.cmd"
LEGACY_AUTOSTART_FILENAME = f"{config.LEGACY_APP_NAMES[0]}.cmd"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA not set")
    return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _pythonw_path() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            return str(pyw)
    return str(exe)


def _command_line() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = Path(__file__).resolve().parent / "main.py"
    return f'"{_pythonw_path()}" "{script}"'


def autostart_file() -> Path:
    _migrate_legacy_autostart()
    return _startup_dir() / AUTOSTART_FILENAME


def _legacy_autostart_file() -> Path:
    return _startup_dir() / LEGACY_AUTOSTART_FILENAME


def _startup_cmd_content() -> str:
    return "@echo off\r\nstart \"\" /b " + _command_line() + "\r\n"


def _write_cmd_file(target: Path) -> None:
    # Newline="" preserves the exact CRLF bytes we write.
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(_startup_cmd_content())


def _migrate_legacy_autostart() -> None:
    legacy = _legacy_autostart_file()
    target = _startup_dir() / AUTOSTART_FILENAME

    if not legacy.exists() or legacy == target:
        return
    if target.exists():
        # Keep the legacy file as a user-visible fallback; never delete data.
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_cmd_file(target)
        legacy.unlink()
    except Exception as exc:
        logger.exception("Failed to migrate autostart file %s -> %s: %s", legacy, target, exc)


def is_enabled() -> bool:
    return autostart_file().exists()


def install() -> Path:
    target = autostart_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_cmd_file(target)
    return target


def remove() -> bool:
    target = autostart_file()
    legacy = _legacy_autostart_file()
    removed = False
    if target.exists():
        target.unlink()
        removed = True
    if legacy.exists():
        legacy.unlink()
        removed = True
    return removed
