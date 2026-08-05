"""Regression tests for legacy authentication settings migration."""

from __future__ import annotations

from pathlib import Path

import auth


def test_existing_target_does_not_delete_legacy_settings(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "settings.json"
    target = tmp_path / "current" / "settings.json"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text('{"password": "legacy"}', encoding="utf-8")
    target.write_text('{"password": "current"}', encoding="utf-8")

    migrated = auth._migrate_from_source(source, target)

    assert migrated is False
    assert source.read_text(encoding="utf-8") == '{"password": "legacy"}'
    assert target.read_text(encoding="utf-8") == '{"password": "current"}'
