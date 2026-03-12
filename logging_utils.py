"""Shared logger setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import config

_CONFIGURED = False


def setup_logging() -> logging.Logger:
    global _CONFIGURED

    logger = logging.getLogger(config.LOGGER_NAME)
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        log_path = config.app_dir() / config.LOG_FILE_NAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.LOG_FILE_MAX_BYTES,
            backupCount=config.LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        logger.warning("Failed to initialize file logging: %s", exc)

    _CONFIGURED = True
    return logger
