"""Helpers for discovering and starting local applications."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import psutil

import config

logger = logging.getLogger(config.LOGGER_NAME)

_HIDDEN_PROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_RECENT_APPS_SCAN_LIMIT = 200


def _normalize_path_key(value: str) -> str:
    return str(value or "").strip().casefold()


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
                    name = [System.IO.Path]::GetFileNameWithoutExtension($target)
                    path = $target
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


def list_recent(limit: int = 12, prioritized_paths: list[str] | None = None) -> list[dict[str, str]]:
    recent_dir = _recent_items_dir()
    if recent_dir is None or not recent_dir.exists():
        base_items: list[dict[str, Any]] = []
    else:
        base_items = _powershell_recent_apps(recent_dir)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw_path in prioritized_paths or []:
        target = Path(str(raw_path or "").strip())
        if not target.is_file() or target.suffix.lower() != ".exe":
            continue
        key = _normalize_path_key(str(target))
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"name": target.stem, "path": str(target)})

    for item in base_items:
        path = str(item.get("path") or "").strip()
        name = str(item.get("name") or "").strip()
        if not path:
            continue
        key = _normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"name": name or Path(path).stem, "path": path})

    max_items = max(1, int(limit))
    return deduped[:max_items]


def start(path: str) -> None:
    target = Path(str(path or "").strip())
    if not target.is_file():
        raise ValueError("application path does not exist")
    if target.suffix.lower() != ".exe":
        raise ValueError("only executable applications are supported")
    try:
        subprocess.Popen([str(target)], shell=False)
    except Exception as exc:
        logger.exception("Failed to start application %s: %s", target, exc)
        raise RuntimeError("failed to start application") from exc


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
