"""Single-instance guard for Windows."""

from __future__ import annotations

import atexit
import ctypes
import os
import sys

_mutex_handle = None
_ERROR_ALREADY_EXISTS = 183
_MUTEX_NAME = "Local\\PCRemoteSingleInstance"


def _show_already_running_message() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "Приложение уже запущено и работает в трее.",
            "PC Remote",
            0x00000040,
        )
    except Exception:
        pass


def acquire() -> bool:
    """Return False when another instance already owns the mutex."""
    global _mutex_handle

    if os.name != "nt":
        return True
    if _mutex_handle:
        return True

    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        return True

    last_error = ctypes.windll.kernel32.GetLastError()
    if last_error == _ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        _show_already_running_message()
        return False

    _mutex_handle = handle
    atexit.register(release)
    return True


def release() -> None:
    global _mutex_handle
    if not _mutex_handle or os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
    except Exception:
        pass
    _mutex_handle = None
