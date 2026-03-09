"""Autostart management for Windows (current user)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PC-Android"
AUTOSTART_FILENAME = f"{APP_NAME}.cmd"


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
    return _startup_dir() / AUTOSTART_FILENAME


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
    if target.exists():
        target.unlink()
        return True
    return False
