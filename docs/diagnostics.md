# Read-only diagnostics

Run `python main.py --diagnostics` (or `python diagnostics.py`) from the source environment. The command prints JSON and exits without starting servers, importing the tray/audio stack, initializing authentication, creating logs, or migrating settings. It can also be used when setup has not completed.

Fields:
- `version`: build version.
- `bind`: configured API/web addresses and ports, not evidence of live listeners.
- `autostart`: current/legacy per-user Startup CMD presence, not evidence of a successful login launch.
- `firewall`: read-only Windows `Get-NetFirewallProfile` / `Get-NetFirewallRule` summary. Rule count matches PC Remote / PC-Android display-name prefixes. It is not an effective permission or reachability check; other program/port/group-policy rules may apply. Failure/timeout is `unknown`, not `disabled`.
- `config`: canonical settings path and existence; no contents.
- `last_error`: category only if an ERROR entry is present in the bounded 64 KiB tail of the current log. Raw log messages are never emitted. Null means no error observed there, not proof of a healthy previous run.

No PINs, hashes, tokens, application command lines, environment dumps or raw exception/PowerShell output are included. Review the user-name-bearing config path before sharing a report publicly.

Verification: `python -m pytest tests/test_diagnostics.py`. These tests include a real child-process CLI invocation with temporary APPDATA and prove settings bytes unchanged and no log created. The firewall query has also been exercised read-only on Windows; actual remote reachability is deliberately not tested.
