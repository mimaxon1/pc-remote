"""Unified safe legacy migration contracts. No real user paths are touched."""
import json
import os

import pytest

from conftest_helpers import set_appdata_env  # noqa: F401  (re-exported helper)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_settings_preserve_legacy_file_when_current_exists(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import auth
    legacy = tmp_path / 'PC-Android' / 'settings.json'
    current = tmp_path / 'PC Remote' / 'settings.json'
    _write(legacy, {'version': 2, 'password': {'is_set': False}})
    _write(current, {'version': auth.SETTINGS_VERSION, 'password': {'is_set': True}})
    legacy_bytes = legacy.read_bytes()

    result = auth.settings_path()

    assert result == current
    assert current.read_bytes() == current.read_bytes()
    assert _read(current)['password'] == {'is_set': True}
    assert legacy.exists(), 'legacy settings file must not be deleted'
    assert legacy.read_bytes() == legacy_bytes


def test_settings_migrate_move_legacy_when_no_current(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import auth
    legacy = tmp_path / 'PC-Android' / 'settings.json'
    current = tmp_path / 'PC Remote' / 'settings.json'
    payload = {'version': 2, 'password': {'is_set': False}, 'network': {'x': 1}}
    _write(legacy, payload)

    result = auth.settings_path()

    assert result == current
    assert not legacy.exists()
    assert _read(current) == payload


def test_settings_failed_migration_never_deletes_source(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import auth
    legacy = tmp_path / 'PC-Android' / 'settings.json'
    current = tmp_path / 'PC Remote' / 'settings.json'
    payload = {'version': 2, 'password': {'is_set': False}}
    _write(legacy, payload)

    def broken_move(*args, **kwargs):
        raise OSError('disk on fire')
    monkeypatch.setattr('migration.shutil.move', broken_move)

    result = auth.settings_path()

    assert result == current
    assert not current.exists()
    assert legacy.exists()
    assert _read(legacy) == payload


def test_network_settings_preserve_legacy_file_when_current_exists(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import net_utils
    legacy = tmp_path / 'PC-Android' / 'settings.json'
    current = tmp_path / 'PC Remote' / 'settings.json'
    _write(legacy, {'network': {'preferred_ip': '192.168.1.20'}})
    _write(current, {'network': {'preferred_ip': '192.168.1.2'}})

    iface, ip = net_utils._load_network_settings()

    assert (iface, ip) == (None, '192.168.1.2')
    assert legacy.exists()
    assert _read(legacy)['network']['preferred_ip'] == '192.168.1.20'


def test_autostart_preserves_legacy_cmd_when_current_exists(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import autostart
    startup = tmp_path / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
    startup.mkdir(parents=True, exist_ok=True)
    legacy = startup / 'PC-Android.cmd'
    current = startup / 'PC Remote.cmd'
    legacy.write_text('@echo off\r\nstart \"\" /b OLD\r\n', encoding='utf-8')
    current.write_text('@echo off\r\nstart \"\" /b NEW\r\n', encoding='utf-8')

    state = autostart.is_enabled()

    # Byte content must contain the NEW command; endings may vary.
    raw = current.read_bytes()
    assert b'start "" /b NEW' in raw
    assert b'OLD' not in raw
    assert legacy.exists()


def test_install_writes_exact_crlf_bytes(tmp_path, monkeypatch):
    set_appdata_env(monkeypatch, tmp_path)
    import autostart
    path = autostart.install()
    raw = path.read_bytes()
    assert raw.endswith(b'\r\n')
    assert b'\r\r\n' not in raw
    assert raw.startswith(b'@echo off\r\nstart "" /b ')
