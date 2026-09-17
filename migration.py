"""Unified safe legacy migration. Sources are moved once and never deleted
when the destination already exists or the move fails."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("pc-remote.migration")


def safe_migrate(source: Path, target: Path) -> bool:
    """Move a legacy file to target without destructive fallbacks.

    Returns True if a move happened, False otherwise. The source is never
    deleted when the target exists or the move fails.
    """
    if not source.exists():
        return False
    try:
        if source.resolve() == target.resolve():
            return False
    except OSError as exc:
        logger.warning("Failed to resolve migration path %s: %s", source, exc)
        return False
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(target))
        return True
    except Exception as exc:
        logger.warning("Failed to migrate %s -> %s: %s", source, target, exc)
        return False
