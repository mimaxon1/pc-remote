# Windows user-scope installer smoke matrix

## Evidence level and safety

**Current result: static contracts and PowerShell safety gates passed; real installer lifecycle NOT RUN.** A passing pytest suite does not prove Inno compilation, Windows login behavior, permissions, upgrade continuity or uninstall cleanup.

Never run the lifecycle on a development workstation. Use a disposable Windows 10/11 x64 VM with a fresh standard-user account, snapshot, no existing PC Remote installation/settings/autostart, and no unrelated firewall/service activity. Reject elevation: an elevated install cannot establish the standard-user requirement. Revert the snapshot between matrix rows. Do not run legacy admin/firewall branch installers as part of this matrix.

The repository's existing release workflow compiles Inno, installs silently, checks HKCU ARP name/version/publisher, and runs uninstall. It does **not** currently verify upgrade/settings/autostart/residual resources, and a `windows-latest` CI account is not proof of a non-admin Windows 10/11 user. The optional harness below is not wired into CI and must not be enabled implicitly.

## Fast, safe verification

From the repository root:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_installer_contract.py tests/test_installer_smoke.py -q
powershell.exe -NoProfile -NonInteractive -File scripts\installer_smoke.ps1
```

The second command only prints JSON with `status: not_run`, `mode: plan-only` and the planned stages. It performs no installation, uninstallation, application CLI call, configuration write or machine inventory. Tests additionally confirm denial with missing consent gates. On platforms without PowerShell those subprocess tests skip; the Inno checks remain static text contracts.

## Automated disposable-VM rows

For **each Windows 10 and Windows 11 x64** standard-user VM, run these rows separately. In every row use a current-lineage previous Setup and a newly built Setup with the unchanged main AppId; supply the expected new ARP version. Using the same installer twice establishes repair/reinstall only, not an actual version upgrade.

| Row | AutostartCase | Install / upgrade requirements | Uninstall requirements | Local evidence |
|---|---|---|---|---|
| A | `disabled` | Default per-user path, HKCU ARP only, Start Menu shortcut, no default desktop icon, no silent launch; startup remains disabled | EXE/ARP/Start Menu removed; settings byte-identical; no autostart; machine inventory unchanged | NOT RUN |
| B | `owned` | Run installed EXE `--install-autostart`; verify target path; seed matching legacy Startup and HKCU Run compatibility entries; upgrade preserves all choices | Generated current/legacy Startup and matching Run value removed, settings retained; no service/firewall changes | NOT RUN |
| C | `foreign` | Seed unrelated/custom Startup files and unrelated Run target; upgrade leaves them alone | Unrelated entries remain byte-identical, installed EXE/ARP/shortcut gone, settings retained; machine inventory unchanged | NOT RUN |

The harness records installer exit codes, artifact SHA-256 hashes, OS version, completed stages, result JSON, Inno logs, and read-only before/after service definitions and firewall rule/application filters. It compares machine state without adding/deleting services/rules. An inventory permission failure is a blocker, not a clean result. Background OS rule changes may cause a conservative failure; inspect evidence rather than weakening assertions.

Fixtures are opaque JSON preservation sentinels in current/legacy app-data. They test **installer byte preservation**, not validity of application settings, PIN authentication, or migration algorithms. Auth and network preferences share `settings.json`; an extra arbitrary JSON file tests that installer cleanup does not broadly delete app-data. The owned row calls the app CLI **before** replacing settings with sentinels, and never launches the server afterward.

### Explicit execution (disposable VM ONLY)

Build both artifacts using the documented PyInstaller/Inno release flow, or transfer trusted release artifacts into the VM and verify their hashes. The upgraded artifact must include the new uninstall event. Both installers must have the supported main AppId `{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}`. The old experimental `{B0D5BE86-E060-4F59-AE9C-78C0E67B4A9D}` is a different installed product, not an upgrade fixture.

In a **non-elevated** PowerShell session inside the disposable VM:

```powershell
# Explicit destructive-lifecycle consent: NEVER set this on a real workstation.
$env:PC_REMOTE_DISPOSABLE_VM = '1'
powershell.exe -NoProfile -NonInteractive -File scripts\installer_smoke.ps1 `
  -Execute -Confirmation I_ACCEPT_DISPOSABLE_VM `
  -Setup 'C:\Artifacts\PC-Remote-OLD-windows-x64-Setup.exe' `
  -UpgradeSetup 'C:\Artifacts\PC-Remote-NEW-windows-x64-Setup.exe' `
  -ExpectedVersion 'NEW' -AutostartCase owned `
  -EvidenceDirectory 'C:\Users\TestUser\smoke-owned'
```

Replace placeholders with actual paths/version and select the row's AutostartCase. The evidence directory must not already exist. The two gates are an explicit human attestation, **not automatic VM detection**. The script refuses existing app/legacy settings, installation, shortcuts, related Startup entries or Run value; do not delete real data to bypass this guard.

On failure, it writes `result.json` if execution reached the evidence phase, exits nonzero, and deliberately leaves state for diagnosis. Preflight errors exit before creating evidence. It never automatically retries uninstall, deletes settings/foreign fixtures, stops processes, or alters firewall/service state. Archive evidence and revert/discard the VM. Foreign entries and preserved settings intentionally remain after row C and all settings-preservation rows.

## Required manual rows (not covered by harness)

| Scenario | Procedure in disposable VM | Required observation / evidence |
|---|---|---|
| Interactive installer | Run wizard as standard user; default install and then repeat with desktop icon selected | No UAC request; default path current-user; correct shortcut creation/removal; capture wizard and ARP evidence |
| Login autostart | Install, opt in via tray/CLI, sign out/in; then disable and sign out/in | Exactly one app process/tray instance when enabled, none when disabled; correct quoted executable path, including a non-ASCII Windows profile |
| Real persisted preferences | Configure a test PIN/network/interface and other preferences through supported app UI; close; upgrade; reopen | Preferences still usable, no new PIN prompt; do not publish hashes or actual settings containing secrets |
| Settings retained on uninstall/reinstall | Uninstall after configuration, verify settings hashes privately, reinstall | Old preferences load; only install-owned files removed; settings deletion is separate explicit user action |
| App running during upgrade/uninstall | Start app, run upgrade/uninstall | Inno CloseApplications behavior and no remaining running app; do not infer this from silent closed-app rows |
| Custom path / Unicode | Install to a user-writable path containing spaces/non-ASCII, opt in, upgrade/uninstall | Startup quoting/UTF-8 comparison correct; unrelated portable installation preserved; log any conservative leftover |
| Read-only or locked Startup artifact | Make only VM test artifact undeletable, uninstall, inspect Inno log | Cleanup failure visible; do not claim no residue if deletion failed; revert VM afterward |
| Firewall prompt interaction | In an isolated trusted test LAN, explicitly approve/deny Windows' own prompt when launching app | Record OS-created rule ownership separately; user installer must not silently create/delete machine rules |
| Legacy admin experimental package | Separate explicitly approved migration investigation only | Not covered: differing AppId/machine rules need an administrative ownership-aware cleanup plan, never blanket name deletion |

## Acceptance and blockers

Release acceptance requires: compiled installer; all automated rows on supported Windows versions under standard users; required manual login/interactive/settings rows; archived actual logs and residual-state checks. Do not mark an unexecuted row passed because a static test checks the corresponding script text.

At review time Inno Setup 6 was absent from PATH and both standard installation locations, and `dist/PC Remote/PC Remote.exe` was absent. No disposable-VM lifecycle was authorized/executed in this work. These block compilation and real runtime sign-off. The local suite's result covers only source contracts, PowerShell parsing/plan-only output and fail-closed gates.

See [branch migration report](../BRANCH_MIGRATION_REPORT.md) for rejected legacy firewall/default-autostart changes and exact cleanup ownership policy.
