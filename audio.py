"""System volume / output-device control for Windows.

We use `pycaw` + `comtypes` to access the default audio endpoint and to switch
the default render device.

Important: COM is thread-affine. FastAPI handlers may run on different threads,
so we initialize/uninitialize COM on every call.
"""

from __future__ import annotations

from ctypes import POINTER, cast
from types import SimpleNamespace
from typing import Callable, TypeVar

try:
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import (
        AudioUtilities,
        DEVICE_STATE,
        EDataFlow,
        ERole,
        IAudioEndpointVolume,
    )
    _AUDIO_BACKEND_AVAILABLE = True
except ImportError:
    comtypes = SimpleNamespace(  # type: ignore[assignment]
        CoInitialize=lambda: None,
        CoUninitialize=lambda: None,
    )
    CLSCTX_ALL = 0  # type: ignore[assignment]
    AudioUtilities = SimpleNamespace(  # type: ignore[assignment]
        GetSpeakers=lambda: None,
        GetAllDevices=lambda *_args, **_kwargs: [],
        SetDefaultDevice=lambda *_args, **_kwargs: None,
    )
    DEVICE_STATE = SimpleNamespace(ACTIVE=SimpleNamespace(value=1))  # type: ignore[assignment]
    EDataFlow = SimpleNamespace(eRender=SimpleNamespace(value=0))  # type: ignore[assignment]
    ERole = SimpleNamespace(  # type: ignore[assignment]
        eConsole=object(),
        eMultimedia=object(),
        eCommunications=object(),
    )
    IAudioEndpointVolume = SimpleNamespace(_iid_=object())  # type: ignore[assignment]
    _AUDIO_BACKEND_AVAILABLE = False

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


def _with_com(action: Callable[[], T], default: T) -> T:
    initialized = False
    try:
        comtypes.CoInitialize()
        initialized = True
        return action()
    except Exception as exc:
        print(f"Audio device error: {exc}")
        return default
    finally:
        if initialized:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


def _default_output_device_info() -> dict[str, str]:
    device = AudioUtilities.GetSpeakers()
    return {
        "id": str(getattr(device, "id", "") or ""),
        "name": str(getattr(device, "FriendlyName", "") or "Unknown output"),
    }


def get_default_output_device() -> dict[str, str]:
    """Return the active default render device."""

    return _with_com(_default_output_device_info, default={"id": "", "name": "Unknown output"})


def list_output_devices() -> list[dict[str, object]]:
    """Return active render devices with the current default highlighted."""

    def action() -> list[dict[str, object]]:
        default_id = _default_output_device_info()["id"]
        devices = AudioUtilities.GetAllDevices(
            EDataFlow.eRender.value,
            DEVICE_STATE.ACTIVE.value,
        )
        items: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for device in devices:
            device_id = str(getattr(device, "id", "") or "")
            if not device_id or device_id in seen_ids:
                continue
            seen_ids.add(device_id)
            name = str(getattr(device, "FriendlyName", "") or "Unknown output")
            items.append(
                {
                    "id": device_id,
                    "name": name,
                    "is_default": device_id == default_id,
                }
            )
        items.sort(key=lambda item: (not bool(item["is_default"]), str(item["name"]).lower()))
        return items

    return _with_com(action, default=[])


def set_default_output_device(device_id: str) -> dict[str, str]:
    """Set the default render device for the common Windows audio roles."""
    target_id = str(device_id or "").strip()
    if not target_id:
        raise ValueError("device_id is required")
    if not _AUDIO_BACKEND_AVAILABLE:
        raise RuntimeError("audio backend is unavailable")

    roles = [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]

    def action() -> dict[str, str]:
        AudioUtilities.SetDefaultDevice(target_id, roles=roles)
        current = _default_output_device_info()
        if current["id"] != target_id:
            raise RuntimeError("default output device did not switch")
        return current

    result = _with_com(action, default={"id": "", "name": ""})
    if not result["id"]:
        raise RuntimeError("failed to switch output device")
    return result


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
