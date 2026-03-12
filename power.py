"""Windows power actions used by the API endpoints."""

from __future__ import annotations

import logging
import subprocess

import config

logger = logging.getLogger(config.LOGGER_NAME)


def _run_shutdown_command(*args: str) -> None:
    try:
        subprocess.run(
            ["shutdown", *args],
            check=True,
            shell=False,
            timeout=config.HTTP_CLIENT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("Power command timed out: %s", exc)
        raise RuntimeError("power command timed out") from exc
    except subprocess.CalledProcessError as exc:
        logger.exception("Power command failed: %s", exc)
        raise RuntimeError("power command failed") from exc


def shutdown() -> None:
    """Shutdown the PC immediately."""
    _run_shutdown_command("/s", "/t", "0")


def reboot() -> None:
    """Reboot the PC immediately."""
    _run_shutdown_command("/r", "/t", "0")
