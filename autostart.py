"""Autostart management for Windows (current user)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import config

logger = logging.getLogger(config.LOGGER_NAME)

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = config.APP_NAME
AUTOSTART_FILENAME = f"{config.APP_NAME}.cmd"
LEGACY_AUTOSTART_FILENAME = f"{config.LEGACY_APP_NAMES[0]}.cmd"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA not set")
    return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _legacy_startup_files() -> tuple[Path, ...]:
    startup = _startup_dir()
    return (
        startup / AUTOSTART_FILENAME,
        startup / LEGACY_AUTOSTART_FILENAME,
    )


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


def _open_run_key(access: int, *, create: bool = False):
    if os.name != "nt":
        raise RuntimeError("Windows autostart is only available on Windows")

    import winreg

    if create:
        return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, access)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, access)


def _read_registry_value() -> str | None:
    if os.name != "nt":
        return None

    import winreg

    try:
        with _open_run_key(winreg.KEY_QUERY_VALUE) as key:
            value, value_type = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Failed to read autostart registry value: %s", exc)
        return None

    if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        return None
    return str(value)


def _write_registry_value(command: str) -> None:
    import winreg

    with _open_run_key(winreg.KEY_SET_VALUE, create=True) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete_registry_value() -> bool:
    if os.name != "nt":
        return False

    import winreg

    try:
        with _open_run_key(winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Failed to remove autostart registry value: %s", exc)
        return False


def _remove_legacy_startup_files() -> bool:
    removed = False
    try:
        candidates = _legacy_startup_files()
    except RuntimeError:
        return False

    for path in candidates:
        if not path.exists():
            continue
        try:
            path.unlink()
            removed = True
        except OSError as exc:
            logger.warning("Failed to remove legacy autostart file %s: %s", path, exc)
    return removed


def _migrate_legacy_autostart() -> None:
    """Move old Startup-folder .cmd autostart to the per-user Run key."""
    try:
        legacy_exists = any(path.exists() for path in _legacy_startup_files())
    except RuntimeError:
        return

    if not legacy_exists:
        return

    if _read_registry_value() is None:
        try:
            _write_registry_value(_command_line())
        except Exception as exc:
            logger.exception("Failed to migrate legacy autostart to registry: %s", exc)
            return

    _remove_legacy_startup_files()


def autostart_location() -> str:
    return rf"HKCU\{RUN_KEY_PATH}\{RUN_VALUE_NAME}"


def is_enabled() -> bool:
    _migrate_legacy_autostart()
    value = _read_registry_value()
    if value is None:
        return False
    return value.strip() == _command_line().strip()


def install() -> str:
    command = _command_line()
    _write_registry_value(command)
    _remove_legacy_startup_files()
    return autostart_location()


def remove() -> bool:
    removed_registry = _delete_registry_value()
    removed_legacy = _remove_legacy_startup_files()
    return removed_registry or removed_legacy
