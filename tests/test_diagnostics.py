"""Read-only diagnostics contracts; no real system changes."""
import json
import subprocess
import sys
from pathlib import Path


def test_diagnostics_cli_is_read_only_and_does_not_echo_settings(tmp_path):
    import os
    import importlib.util
    assert importlib.util.find_spec('diagnostics') is not None, 'read-only diagnostics module missing'
    folder = tmp_path / 'PC Remote'
    folder.mkdir()
    settings = folder / 'settings.json'
    settings.write_text('{"password": "DO_NOT_PRINT_SECRET"}', encoding='utf-8')
    before = settings.read_bytes()
    env = dict(os.environ, APPDATA=str(tmp_path), LOCALAPPDATA=str(tmp_path))
    result = subprocess.run([sys.executable, 'main.py', '--diagnostics'],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['version']
    assert report['config']['path'] == str(settings)
    assert report['bind']['api']['port'] == 8000
    assert report['autostart']['state'] == 'disabled'
    assert 'DO_NOT_PRINT_SECRET' not in result.stdout + result.stderr
    assert settings.read_bytes() == before
    assert not (folder / 'pc-remote.log').exists()


def test_diagnostics_reports_error_category_not_log_text(tmp_path, monkeypatch):
    import config
    import diagnostics
    monkeypatch.setattr(config, 'app_dir', lambda: tmp_path)
    (tmp_path / config.LOG_FILE_NAME).write_text(
        '2026-09-17 12:00:00,000 - ERROR - failure secret-pin-and-token\n', encoding='utf-8')
    result = diagnostics.collect_diagnostics()
    assert result['last_error'] == {'state': 'recorded', 'code': 'application_error',
                                    'detail': 'omitted_for_privacy'}
    assert 'secret-pin-and-token' not in json.dumps(result)


def test_firewall_probe_parses_summary_only(monkeypatch):
    import diagnostics
    def run(args, **kwargs):
        assert args[0].lower().endswith('powershell.exe')
        assert 'Get-NetFirewallRule' in args[-1]
        assert 'New-NetFirewallRule' not in args[-1]
        return subprocess.CompletedProcess(args, 0, '{"enabled_profiles":3,"app_rules":0}', '')
    monkeypatch.setattr(diagnostics.subprocess, 'run', run)
    assert diagnostics.firewall_status() == {
        'state': 'observed', 'enabled_profiles': 3, 'app_rules': 0,
        'effective_reachability': 'not_tested'}


def test_firewall_failure_never_echoes_command_stderr(monkeypatch):
    import diagnostics
    monkeypatch.setattr(diagnostics.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a, 1, '', 'secret-error'))
    assert diagnostics.firewall_status() == {'state': 'unknown', 'reason': 'query_failed'}
