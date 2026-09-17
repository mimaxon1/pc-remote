"""Read-only diagnostics. Never initialize authentication or migrate settings.

Secrets policy: this module must never echo PIN hashes, session tokens,
settings.json contents or application log text. Errors are reported as
categories, never as raw messages.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import config

_FIREWALL_PS = (
    "$ErrorActionPreference='Stop'; "
    "$profiles=@(Get-NetFirewallProfile | Where-Object Enabled -eq True); "
    "$rules=@(Get-NetFirewallRule | Where-Object {"
    "$_.DisplayName -like 'PC Remote*' -or $_.DisplayName -like 'PC-Android*'}); "
    "@{enabled_profiles=$profiles.Count;app_rules=$rules.Count} | ConvertTo-Json -Compress"
)


def firewall_status() -> dict:
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _FIREWALL_PS],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {'state': 'unknown', 'reason': 'query_failed'}
    if result.returncode != 0:
        return {'state': 'unknown', 'reason': 'query_failed'}
    try:
        data = json.loads(result.stdout or '{}')
    except ValueError:
        return {'state': 'unknown', 'reason': 'query_failed'}
    if not isinstance(data, dict) or any(
        type(data.get(key)) is not int or data[key] < 0
        for key in ('enabled_profiles', 'app_rules')
    ):
        return {'state': 'unknown', 'reason': 'query_failed'}
    return {
        'state': 'observed',
        'enabled_profiles': data['enabled_profiles'],
        'app_rules': data['app_rules'],
        'effective_reachability': 'not_tested',
    }


def _last_error_state() -> dict | None:
    path = config.app_dir() / config.LOG_FILE_NAME
    try:
        with path.open('rb') as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 65536))
            for line in reversed(handle.read().decode('utf-8', errors='replace').splitlines()):
                if ' - ERROR - ' in line:
                    return {'state': 'recorded', 'code': 'application_error',
                            'detail': 'omitted_for_privacy'}
    except OSError:
        pass
    return None


def collect_diagnostics() -> dict:
    path = config.app_dir() / config.SETTINGS_FILENAME
    startup = Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs/Startup'
    names = (config.APP_NAME, *config.LEGACY_APP_NAMES)
    enabled = bool(os.environ.get('APPDATA')) and any(
        (startup / f'{name}.cmd').is_file() for name in names
    )
    return {
        'version': config.APP_VERSION,
        'bind': {
            'api': {'address': config.API_HOST, 'port': config.API_PORT},
            'web': {'address': config.WEB_HOST, 'port': config.WEB_PORT},
        },
        'autostart': {'state': 'enabled' if enabled else 'disabled'},
        'firewall': firewall_status(),
        'config': {'path': str(path), 'exists': path.is_file()},
        'last_error': _last_error_state(),
    }


def main() -> int:
    print(json.dumps(collect_diagnostics(), ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
