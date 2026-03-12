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


def _migrate_legacy_autostart() -> None:
    legacy = _legacy_autostart_file()
    target = _startup_dir() / AUTOSTART_FILENAME

    if not legacy.exists() or legacy == target:
        return
    if target.exists():
        try:
            legacy.unlink()
        except Exception as exc:
            logger.warning("Failed to remove legacy autostart file %s: %s", legacy, exc)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = f'@echo off\r\nstart "" /b {_command_line()}\r\n'
        target.write_text(content, encoding="utf-8")
        legacy.unlink()
    except Exception as exc:
        logger.exception("Failed to migrate autostart file %s -> %s: %s", legacy, target, exc)


def is_enabled() -> bool:
    return autostart_file().exists()


def install() -> Path:
    target = autostart_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = _command_line()
    content = f'@echo off\r\nstart "" /b {cmd}\r\n'
    target.write_text(content, encoding="utf-8")
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
