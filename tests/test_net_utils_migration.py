"""Regression tests for legacy network settings migration."""

from __future__ import annotations

from pathlib import Path

import net_utils


def test_existing_target_does_not_delete_legacy_network_settings(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "settings.json"
    target = tmp_path / "current" / "settings.json"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text('{"network": {"preferred_interface": "Ethernet"}}', encoding="utf-8")
    target.write_text('{broken json', encoding="utf-8")

    migrated = net_utils._migrate_from_source(source, target)

    assert migrated is False
    assert source.exists()
    assert source.read_text(encoding="utf-8") == '{"network": {"preferred_interface": "Ethernet"}}'
    assert target.read_text(encoding="utf-8") == '{broken json'
