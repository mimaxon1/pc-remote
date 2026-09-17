"""Shared pytest helpers for migration tests."""
from __future__ import annotations

import os


def set_appdata_env(monkeypatch, tmp_path):
    """Point all per-user app dirs at the test sandbox."""
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))


def setenv(name, value):
    return os.environ.__setitem__(name, value)
