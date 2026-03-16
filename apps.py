"""Helpers for discovering and starting local applications."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import psutil

import config

logger = logging.getLogger(config.LOGGER_NAME)

_HIDDEN_PROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_RECENT_APPS_SCAN_LIMIT = 200
_PINNED_APPS_FILENAME = "pinned_apps.json"
_PINNED_APPS_LIMIT = 8
_PINNED_APPS_LOCK = threading.Lock()
_EXCLUDED_AUMID_FRAGMENTS = (
    "immersivecontrolpanel",
    "microsoft.windows.search",
    "windows.search",
)
_EXCLUDED_NAME_FRAGMENTS = ("powertoys",)
_EXCLUDED_PROCESS_NAMES = {
    "applicationframehost.exe",
    "backgroundtaskhost.exe",
    "cmd.exe",
    "conhost.exe",
    "csrss.exe",
    "dllhost.exe",
    "explorer.exe",
    "fontdrvhost.exe",
    "lockapp.exe",
    "lsass.exe",
    "powershell.exe",
    "pwsh.exe",
    "registry",
    "runtimebroker.exe",
    "searchapp.exe",
    "searchfilterhost.exe",
    "searchhost.exe",
    "searchindexer.exe",
    "searchprotocolhost.exe",
    "services.exe",
    "shellexperiencehost.exe",
    "smss.exe",
    "startmenuexperiencehost.exe",
    "svchost.exe",
    "system",
    "system idle process",
    "systemsettings.exe",
    "taskhostw.exe",
    "textinputhost.exe",
    "wininit.exe",
    "winlogon.exe",
    "widgets.exe",
    "widgetservice.exe",
    "wireguardservice.exe",
}


def _normalize_path_key(value: str) -> str:
    return str(value or "").strip().casefold()


def _powershell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _name_keys(value: str | None) -> set[str]:
    raw = _clean_text(value).casefold()
    if not raw:
        return set()
    keys = {raw}
    if raw.endswith(".exe"):
        keys.add(raw[:-4])
    else:
        keys.add(f"{raw}.exe")
    return keys


def _is_user_launch_candidate(target: Path, name: str | None = None, aumid: str | None = None) -> bool:
    aumid_key = _clean_text(aumid).casefold()
    if aumid_key and any(fragment in aumid_key for fragment in _EXCLUDED_AUMID_FRAGMENTS):
        return False

    keys = set()
    if not aumid_key:
        keys.update(_name_keys(target.name))
        keys.update(_name_keys(target.stem))
    keys.update(_name_keys(name))
    keys.update(_name_keys(aumid))
    if any(fragment in key for key in keys for fragment in _EXCLUDED_NAME_FRAGMENTS):
        return False
    return not any(key in _EXCLUDED_PROCESS_NAMES for key in keys)


def _normalize_app_item(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None

    path = _clean_text(item.get("path"))
    if not path:
        return None

    target = Path(path)
    if target.suffix.lower() != ".exe" or not target.is_file():
        return None
    name = _clean_text(item.get("name")) or target.stem
    args = _clean_text(item.get("args"))
    aumid = _clean_text(item.get("aumid"))
    if not _is_user_launch_candidate(target, name, aumid):
        return None

    normalized = {
        "name": name,
        "path": str(target),
    }
    if args:
        normalized["args"] = args
    if aumid:
        normalized["aumid"] = aumid
    return normalized


def _validate_executable_path(path: str | None) -> Path:
    target = Path(str(path or "").strip())
    if not target.is_file():
        raise ValueError("application path does not exist")
    if target.suffix.lower() != ".exe":
        raise ValueError("only executable applications are supported")
    return target


def _validate_launch_item(
    path: str | None,
    *,
    name: str | None = None,
    args: str | None = None,
    aumid: str | None = None,
) -> dict[str, str]:
    target = _validate_executable_path(path)
    normalized = _normalize_app_item(
        {
            "name": name or target.stem,
            "path": str(target),
            "args": args,
            "aumid": aumid,
        }
    )
    if normalized is None:
        raise ValueError("application is not suitable for quick launch")
    return normalized


def _launch_signature(item: dict[str, Any]) -> str:
    aumid = _clean_text(item.get("aumid")).casefold()
    if aumid:
        return f"aumid:{aumid}"
    path = _normalize_path_key(item.get("path"))
    args = _clean_text(item.get("args")).casefold()
    return f"path:{path}|args:{args}"


def _normalize_argument_text(value: Any) -> str:
    text = _clean_text(value).replace('"', " ").replace("'", " ")
    return " ".join(text.split()).casefold()


def _command_line_matches(expected_args: str | None, cmdline: Any) -> bool:
    expected = _normalize_argument_text(expected_args)
    if not expected:
        return True

    if isinstance(cmdline, (list, tuple)):
        actual_raw = " ".join(str(part or "") for part in cmdline[1:])
    else:
        actual_raw = _clean_text(cmdline)
    actual = _normalize_argument_text(actual_raw)
    if not actual:
        return False
    if expected in actual:
        return True

    expected_tokens = [token for token in expected.split() if len(token) >= 3]
    return bool(expected_tokens) and all(token in actual for token in expected_tokens)


def _matching_process_pids(item: dict[str, Any]) -> set[int]:
    target_key = _normalize_path_key(item.get("path"))
    expected_args = _clean_text(item.get("args"))
    current_user = _current_user_key()
    pids: set[int] = set()

    for process in psutil.process_iter(["pid", "exe", "cmdline", "username"]):
        try:
            info = process.info
            pid = int(info.get("pid") or 0)
            if pid <= 0:
                continue

            exe = _clean_text(info.get("exe"))
            if _normalize_path_key(exe) != target_key:
                continue

            username = _clean_text(info.get("username")).casefold()
            if current_user and username and username != current_user:
                continue

            if not _command_line_matches(expected_args, info.get("cmdline")):
                continue

            pids.add(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            logger.debug("Failed to match process for app window control: %s", exc)
            continue

    return pids


def _window_handles_by_pid() -> dict[int, list[int]]:
    if os.name != "nt":
        return {}

    handles: dict[int, list[int]] = {}
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                handles.setdefault(int(pid.value), []).append(int(hwnd))
            return True

        callback = callback_type(_visit_window)
        user32.EnumWindows(callback, 0)
    except Exception as exc:
        logger.debug("Failed to enumerate app windows: %s", exc)
        return {}

    return handles


def _matching_window_handles(item: dict[str, Any]) -> list[int]:
    pids = _matching_process_pids(item)
    if not pids:
        return []

    handles_by_pid = _window_handles_by_pid()
    handles: list[int] = []
    for pid in sorted(pids):
        handles.extend(handles_by_pid.get(pid, []))
    return handles


def _control_existing_window(item: dict[str, Any], action: str) -> bool:
    if os.name != "nt":
        return False

    handles = _matching_window_handles(item)
    if not handles:
        return False

    try:
        import ctypes

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        SW_MINIMIZE = 6
        WM_CLOSE = 0x0010

        if action == "activate":
            hwnd = handles[0]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            return True

        if action == "minimize":
            for hwnd in handles:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            return True

        if action == "close":
            for hwnd in handles:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return True
    except Exception as exc:
        logger.debug("Failed to control app window for %s: %s", item.get("name"), exc)
        return False

    return False


def _pinned_apps_path() -> Path:
    return config.app_dir() / _PINNED_APPS_FILENAME


def _is_windows_apps_path(target: Path) -> bool:
    return "\\windowsapps\\" in _normalize_path_key(str(target))


def _start_packaged_app(target: Path) -> bool:
    if os.name != "nt":
        return False

    script = rf"""
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath({_powershell_quote(str(target))})
$package = Get-AppxPackage | Where-Object {{
    $location = [string]$_.InstallLocation
    -not [string]::IsNullOrWhiteSpace($location) -and
    $target.StartsWith(
        [System.IO.Path]::GetFullPath($location),
        [System.StringComparison]::OrdinalIgnoreCase
    )
}} | Select-Object -First 1
if (-not $package) {{
    exit 3
}}
$applications = @((Get-AppxPackageManifest -Package $package.PackageFullName).Package.Applications.Application)
if (-not $applications -or $applications.Count -eq 0) {{
    exit 4
}}
$targetName = [System.IO.Path]::GetFileName($target)
$app = $applications | Where-Object {{
    $executable = [string]$_.Executable
    -not [string]::IsNullOrWhiteSpace($executable) -and
    [System.IO.Path]::GetFileName($executable).Equals(
        $targetName,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}} | Select-Object -First 1
if (-not $app) {{
    $app = $applications | Select-Object -First 1
}}
$aumid = "$($package.PackageFamilyName)!$($app.Id)"
Start-Process explorer.exe "shell:AppsFolder\$aumid"
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
            check=False,
            creationflags=_HIDDEN_PROCESS_FLAGS,
        )
    except Exception as exc:
        logger.warning("Failed to resolve packaged app launcher for %s: %s", target, exc)
        return False

    if completed.returncode == 0:
        return True

    details = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
    logger.warning("Packaged app launcher failed for %s: %s", target, details)
    return False


def _read_pinned_apps_unlocked() -> list[dict[str, str]]:
    path = _pinned_apps_path()
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read pinned apps from %s: %s", path, exc)
        return []

    if not isinstance(raw, list):
        logger.warning("Pinned apps file %s must contain a JSON array", path)
        return []

    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_item in raw:
        item = _normalize_app_item(raw_item)
        if item is None:
            continue

        key = _launch_signature(item)
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    return items[:_PINNED_APPS_LIMIT]


def _write_pinned_apps_unlocked(items: list[dict[str, str]]) -> None:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_item in items:
        item = _normalize_app_item(raw_item)
        if item is None:
            continue

        key = _launch_signature(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)

    normalized = normalized[:_PINNED_APPS_LIMIT]
    path = _pinned_apps_path()

    if not normalized:
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to remove pinned apps file %s: %s", path, exc)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _recent_items_dir() -> Path | None:
    if os.name != "nt":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Recent"


def _powershell_recent_apps(recent_dir: Path) -> list[dict[str, Any]]:
    escaped_recent_dir = str(recent_dir).replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'Stop'
$recentDir = '{escaped_recent_dir}'
$shell = New-Object -ComObject WScript.Shell
$items = Get-ChildItem -LiteralPath $recentDir -Filter *.lnk -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First {_RECENT_APPS_SCAN_LIMIT} |
    ForEach-Object {{
        try {{
            $shortcut = $shell.CreateShortcut($_.FullName)
            $target = $shortcut.TargetPath
            $arguments = [string]$shortcut.Arguments
            $aumid = ''
            if (-not [string]::IsNullOrWhiteSpace($arguments)) {{
                if ($arguments -match 'shell:AppsFolder\\([^"\s]+)') {{
                    $aumid = $matches[1]
                }}
            }}
            if (
                -not [string]::IsNullOrWhiteSpace($target) -and
                [string]::Equals(
                    [System.IO.Path]::GetExtension($target),
                    '.exe',
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -and
                (Test-Path -LiteralPath $target -PathType Leaf)
            ) {{
                [pscustomobject]@{{
                    name = $_.BaseName
                    path = $target
                    args = $arguments
                    aumid = $aumid
                    last_opened = [System.DateTimeOffset]::new($_.LastWriteTimeUtc).ToUnixTimeSeconds()
                }}
            }}
        }} catch {{
        }}
    }}
@($items) | ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
            creationflags=_HIDDEN_PROCESS_FLAGS,
        )
    except Exception as exc:
        logger.warning("Failed to inspect Windows recent items: %s", exc)
        return []

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if stderr:
            logger.warning("PowerShell recent app scan failed: %s", stderr)
        return []

    payload = completed.stdout.strip() or "[]"
    try:
        parsed = json.loads(payload)
    except Exception as exc:
        logger.warning("Failed to parse recent app list: %s", exc)
        return []

    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _list_shortcut_apps() -> list[dict[str, Any]]:
    recent_dir = _recent_items_dir()
    if recent_dir is None or not recent_dir.exists():
        return []

    items: list[dict[str, Any]] = []
    for raw_item in _powershell_recent_apps(recent_dir):
        normalized = _normalize_app_item(raw_item)
        if normalized is None:
            continue
        items.append(
            {
                **normalized,
                "last_opened": float(raw_item.get("last_opened") or 0.0),
            }
        )
    return items


def _current_user_key() -> str | None:
    try:
        username = str(psutil.Process(os.getpid()).username() or "").strip()
    except Exception:
        return None
    return username.casefold() or None


def _visible_window_pids() -> set[int] | None:
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        visible: set[int] = set()
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                visible.add(int(pid.value))
            return True

        callback = callback_type(_visit_window)
        user32.EnumWindows(callback, 0)
        return visible
    except Exception as exc:
        logger.debug("Failed to inspect visible windows: %s", exc)
        return None


def _list_running_apps() -> list[dict[str, Any]]:
    current_pid = os.getpid()
    current_user = _current_user_key()
    current_exe_key = _normalize_path_key(sys.executable)
    visible_window_pids = _visible_window_pids()
    items: list[dict[str, Any]] = []

    for process in psutil.process_iter(["pid", "name", "exe", "create_time", "username"]):
        try:
            info = process.info
            pid = int(info.get("pid") or 0)
            if pid == current_pid:
                continue
            if visible_window_pids is not None and pid not in visible_window_pids:
                continue

            exe = str(info.get("exe") or "").strip()
            if not exe:
                continue
            target = Path(exe)
            if target.suffix.lower() != ".exe" or not target.is_file():
                continue

            exe_key = _normalize_path_key(str(target))
            if exe_key == current_exe_key:
                continue

            process_name = str(info.get("name") or target.name).strip()
            if not _is_user_launch_candidate(target, process_name):
                continue

            username = str(info.get("username") or "").strip().casefold()
            if current_user and username and username != current_user:
                continue

            create_time = float(info.get("create_time") or 0.0)
            items.append(
                {
                    "name": target.stem,
                    "path": str(target),
                    "last_opened": create_time,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            logger.debug("Failed to inspect process for app list: %s", exc)
            continue

    items.sort(key=lambda item: float(item.get("last_opened") or 0.0), reverse=True)
    return items


def list_recent(
    limit: int = 12,
    prioritized_paths: list[str] | None = None,
    prioritized_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    base_items = _list_shortcut_apps()
    running_items = _list_running_apps()

    candidates: list[dict[str, Any]] = []
    priority_base = time.time() + 1_000_000.0

    for index, raw_item in enumerate(prioritized_items or []):
        normalized = _normalize_app_item(raw_item)
        if normalized is None:
            continue
        candidates.append(
            {
                **normalized,
                "last_opened": priority_base - index,
            }
        )

    for index, raw_path in enumerate(prioritized_paths or []):
        try:
            normalized = _validate_launch_item(raw_path)
        except ValueError:
            continue
        candidates.append(
            {
                **normalized,
                "last_opened": priority_base - index,
            }
        )

    candidates.extend(running_items)
    candidates.extend(base_items)

    candidates.sort(key=lambda item: float(item.get("last_opened") or 0.0), reverse=True)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = _normalize_app_item(item)
        if normalized is None:
            continue
        key = _launch_signature(normalized)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    max_items = max(1, int(limit))
    return deduped[:max_items]


def list_pinned() -> list[dict[str, str]]:
    with _PINNED_APPS_LOCK:
        return _read_pinned_apps_unlocked()


def pin(path: str, *, name: str | None = None, args: str | None = None, aumid: str | None = None) -> dict[str, str]:
    item = _validate_launch_item(path, name=name, args=args, aumid=aumid)
    key = _launch_signature(item)

    with _PINNED_APPS_LOCK:
        existing = _read_pinned_apps_unlocked()
        updated = [item]
        updated.extend(app for app in existing if _launch_signature(app) != key)
        _write_pinned_apps_unlocked(updated)
        return item


def unpin(path: str, *, args: str | None = None, aumid: str | None = None) -> bool:
    target_path = _clean_text(path)
    if not target_path:
        raise ValueError("application path is required")

    key = _launch_signature({"path": target_path, "args": args, "aumid": aumid})
    with _PINNED_APPS_LOCK:
        existing = _read_pinned_apps_unlocked()
        updated = [item for item in existing if _launch_signature(item) != key]
        if len(updated) == len(existing):
            return False
        _write_pinned_apps_unlocked(updated)
        return True


def _resolve_start_item(
    path: str | None,
    *,
    name: str | None = None,
    args: str | None = None,
    aumid: str | None = None,
) -> dict[str, str]:
    raw_path = _clean_text(path)
    if raw_path:
        return _validate_launch_item(raw_path, name=name, args=args, aumid=aumid)

    recent = list_recent(limit=1)
    if not recent:
        raise ValueError("no recently used applications found")
    return recent[0]


def _start_aumid(aumid: str) -> None:
    subprocess.Popen(["explorer.exe", fr"shell:AppsFolder\{aumid}"], shell=False)


def _start_executable(target: Path, args: str | None = None) -> None:
    argument_line = _clean_text(args)
    if argument_line and hasattr(os, "startfile"):
        os.startfile(str(target), arguments=argument_line)
        return
    subprocess.Popen([str(target)], shell=False)


def window_action(
    action: str,
    path: str | None = None,
    *,
    name: str | None = None,
    args: str | None = None,
    aumid: str | None = None,
) -> dict[str, str]:
    if action not in {"minimize", "close"}:
        raise ValueError("unsupported app window action")

    item = _resolve_start_item(path, name=name, args=args, aumid=aumid)
    if not _control_existing_window(item, action):
        raise ValueError("application window not found")
    return item


def start(
    path: str | None = None,
    *,
    name: str | None = None,
    args: str | None = None,
    aumid: str | None = None,
) -> dict[str, str]:
    item = _resolve_start_item(path, name=name, args=args, aumid=aumid)
    target = Path(item["path"])
    try:
        if _control_existing_window(item, "activate"):
            return item
        if item.get("aumid"):
            _start_aumid(item["aumid"])
        elif _is_windows_apps_path(target):
            if not _start_packaged_app(target):
                raise RuntimeError("failed to start packaged application")
        else:
            _start_executable(target, item.get("args"))
    except Exception as exc:
        logger.exception("Failed to start application %s: %s", target, exc)
        raise RuntimeError("failed to start application") from exc
    return item


def kill(process_name: str) -> None:
    target_name = str(process_name or "").strip()
    if not target_name:
        raise ValueError("process_name is required")

    killed = False
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == target_name:
            process.kill()
            killed = True

    if not killed:
        raise ValueError("process not found")
