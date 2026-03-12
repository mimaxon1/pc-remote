"""Helpers for starting and stopping local applications."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import psutil

import config

logger = logging.getLogger(config.LOGGER_NAME)


def start(path: str) -> None:
    target = Path(str(path or "").strip())
    if not target.is_file():
        raise ValueError("application path does not exist")
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
