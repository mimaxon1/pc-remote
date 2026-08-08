from __future__ import annotations

import autostart


def test_existing_target_does_not_delete_legacy_autostart(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "_startup_dir", lambda: tmp_path)

    legacy = tmp_path / autostart.LEGACY_AUTOSTART_FILENAME
    target = tmp_path / autostart.AUTOSTART_FILENAME
    legacy.write_text("legacy-working", encoding="utf-8")
    target.write_text("broken-current", encoding="utf-8")

    autostart._migrate_legacy_autostart()

    assert legacy.read_text(encoding="utf-8") == "legacy-working"
    assert target.read_text(encoding="utf-8") == "broken-current"
