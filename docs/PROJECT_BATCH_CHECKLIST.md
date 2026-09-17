# PC Remote batch audit

Base: origin/main `d728079`; branch `hermes/pc-remote-project-batch-20260917`.
Original checkout `pc-with-android` has uncommitted work and corrupt refs; untouched. Fresh clone used. README requires Python 3.13+; baseline on isolated 3.13.14 environment: 107 passed, 2 third-party deprecation warnings. No AGENTS or current ROADMAP tracked.

## Initial checklist

| Task | State | Evidence / next action |
|---|---|---|
| 1 Security | PARTIAL | SECURITY.md exists; trusted-LAN HTTP is intentional. Review authentication/command/install boundaries; remediate only confirmed defects. |
| 2 Migration | PARTIAL | auth.py and autostart.py contain separate legacy migration, swallowed errors and source deletion; network fix branch needs comparison. |
| 3 Branch report | TODO | 11 legacy installer/autostart/firewall/settings branches available; compare against current main, no bulk merges. |
| 4 Diagnostics | TODO | Only autostart-status CLI exists; add read-only JSON command with no secret values. |
| 5 Installation matrix | PARTIAL | Current release CI covers installation metadata; installer has no uninstall autostart cleanup. Add safe contracts and disposable-Windows smoke harness. |

Real install/uninstall validation requires a disposable Windows user/VM: do not modify this workstation's actual autostart, firewall, services or user configuration. Mock/static tests are not OS lifecycle proof.
