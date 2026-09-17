# PC Remote batch audit

Base: origin/main `d728079`; branch `hermes/pc-remote-project-batch-20260917`.
Original checkout `pc-with-android` has uncommitted work and corrupt refs; untouched. Fresh clone used. README requires Python 3.13+; baseline on isolated 3.13.14 environment: 107 passed, 2 third-party deprecation warnings. No AGENTS or current ROADMAP tracked.

## Initial checklist

| Task | State | Evidence / next action |
|---|---|---|
| 1 Security | DONE | Confirmed defects fixed: legacy PIN attempt budget (serialized), explicit browser Origin rejection, `proxy_headers=False`. `SECURITY.md` + `docs/SECURITY_REVIEW.md` + `tests/test_security_contract.py`. |
| 2 Migration | DONE | Unified `migration.safe_migrate`; auth raises `SettingsError` when a legacy file remains and the destination is missing (no silent reset). Network leftover is preserved and ignored with a warning. Autostart never deletes a colliding legacy CMD. Tests: `tests/test_migration.py`. |
| 3 Branch report | DONE | `BRANCH_MIGRATION_REPORT.md` over 12 topic refs vs `d728079`. No bulk merges. Installer keeps main AppId/user-scope. |
| 4 Diagnostics | DONE | `python main.py --diagnostics` / `diagnostics.py`; no secrets. Tests: `tests/test_diagnostics.py`. |
| 5 Installation matrix | PARTIAL / BLOCKED (VM) | Static Inno contracts + opt-in disposable-VM harness (`scripts/installer_smoke.ps1`, `docs/installer-smoke.md`). Real Inno compile + lifecycle not run here (no ISCC, no `dist/PC Remote/PC Remote.exe`, no disposable VM). |

Real install/uninstall validation requires a disposable Windows user/VM: do not modify this workstation's actual autostart, firewall, services or user configuration. Mock/static tests are not OS lifecycle proof.
