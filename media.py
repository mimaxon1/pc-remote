"""Media key helpers (play/pause/next/prev)."""

from __future__ import annotations

from pynput.keyboard import Controller, Key

_keyboard = Controller()

_KEY_MAP = {
    "play_pause": Key.media_play_pause,
    "next": Key.media_next,
    "prev": Key.media_previous,
    "stop": Key.media_stop,
}


def send(action: str) -> None:
    key = _KEY_MAP.get(action)
    if not key:
        raise ValueError("unsupported action")
    _keyboard.press(key)
    _keyboard.release(key)
