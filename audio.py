"""System volume / mute control for Windows.

We use `pycaw` + `comtypes` to access the default audio endpoint
(`IAudioEndpointVolume`).

Important: COM is thread-affine. FastAPI handlers may run on different threads,
so we initialize/uninitialize COM on every call.
"""

from __future__ import annotations

from ctypes import POINTER, cast
from typing import Callable, TypeVar

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

T = TypeVar("T")


def _with_endpoint(action: Callable[[object], T], default: T) -> T:
    """Open IAudioEndpointVolume and run `action(endpoint)`.

    Returns `default` when the audio endpoint can't be opened (e.g. no audio
    device, COM error, etc.).
    """
    initialized = False
    try:
        # Initialize COM for the current thread
        comtypes.CoInitialize()
        initialized = True
        device = AudioUtilities.GetSpeakers()

        # pycaw versions differ:
        # - older: GetSpeakers() returns IMMDevice with .Activate
        # - newer: returns AudioDevice wrapper with .EndpointVolume (and underlying ._dev)
        endpoint = None
        if hasattr(device, "EndpointVolume"):
            endpoint = device.EndpointVolume
        elif hasattr(device, "Activate"):
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(interface, POINTER(IAudioEndpointVolume))
        elif hasattr(device, "_dev") and hasattr(device._dev, "Activate"):
            interface = device._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(interface, POINTER(IAudioEndpointVolume))

        if endpoint is None:
            raise RuntimeError("Could not get IAudioEndpointVolume endpoint")
        return action(endpoint)
    except Exception as exc:
        print(f"Audio error: {exc}")
        return default
    finally:
        if initialized:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


def get_volume() -> float:
    """Return current volume (0.0-1.0)."""
    def action(endpoint):
        return float(endpoint.GetMasterVolumeLevelScalar())

    return _with_endpoint(action, default=0.0)


def set_volume(value: float):
    """Set volume (0.0-1.0)."""
    value = max(0.0, min(1.0, value))

    def action(endpoint):
        endpoint.SetMasterVolumeLevelScalar(value, None)

    _with_endpoint(action, default=None)


def is_muted() -> bool:
    """Return True if muted."""
    def action(endpoint):
        return bool(endpoint.GetMute())

    return _with_endpoint(action, default=False)


def mute():
    """Mute system audio."""
    def action(endpoint):
        endpoint.SetMute(1, None)

    _with_endpoint(action, default=None)


def unmute():
    """Unmute system audio."""
    def action(endpoint):
        endpoint.SetMute(0, None)

    _with_endpoint(action, default=None)


def toggle_mute() -> bool:
    """Toggle mute and return new state."""
    def action(endpoint):
        current = bool(endpoint.GetMute())
        new_state = not current
        endpoint.SetMute(1 if new_state else 0, None)
        return new_state

    return _with_endpoint(action, default=False)
