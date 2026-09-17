# Legacy branch migration review

Reviewed against **origin/main `d7280791dc2b0b6b08e3e7dae1f1230813aaa362`** on 2026-09-17. Working branch: `hermes/pc-remote-project-batch-20260917`. No merges, cherry-picks, branch switches, commits, stash operations or pushes were performed in this review.

## Method and accounting

Read README, `packaging/README.md`, `docs/testing.md`, `.github/workflows/release.yml`, current implementation, and individual legacy diffs. For every remote topic ref, ran `git merge-base --is-ancestor <ref> origin/main`, `git log origin/main..<ref>`, `git cherry origin/main <ref>`, and inspected relevant file diffs/commits. All comparisons below are against the pinned main, not concurrently changing batch work.

There are **12 topic refs**, not 11: nine `agent/*` and three `fix/*`. Five names point at the same already-contained commit. The remaining seven tips have 12 distinct out-of-main commits after deduplicating shared installer commits. `git cherry` marks every one `+`: **none is patch-equivalent to a main commit**. That does not mean every change is valuable: main implements some equivalent functionality differently.

## Branch disposition

| Remote branch (prefix `origin/`) | Tip | Main relationship / individual work | Decision |
|---|---|---|---|
| `agent/windows-installer` | `7b493f4` | `+ 2ee77ae` Inno template; `+ 7b493f4` build helper | **Superseded in purpose, not patch-equivalent.** Keep main's installer and release workflow. Do not introduce the alternate product identity or duplicate helper. |
| `agent/installer-firewall` | `9bdebd2` | Shared two installer commits; `+ 9bdebd2` admin install and netsh rules | **Reject machine-scope behavior.** Contradicts per-user/no-elevation contract; see firewall analysis below. |
| `agent/installer-autostart` | `69964a1` | Shared two installer commits; `+ b9b2b04` unconditional HKCU Run registration; `+ 69964a1` stacks firewall/admin behavior | **Reject wholesale.** Do not silently enable autostart or import admin firewall logic. Retain the idea of uninstall cleanup only, adapted with ownership checks. |
| `agent/registry-autostart` | `7dfb81b` | `+ 7dfb81b` replaces Startup `.cmd` implementation with HKCU Run | **Defer backend migration.** Not a fix required for current installer. Requires coordinated API/status/legacy conflict policy and behavioral tests. |
| `agent/windows-installer-docs` | `8717e1f` | Ancestor; zero unique commits; empty `git cherry` | **Already contained.** Ref name does not establish that installer work exists here. |
| `agent/windows-installer-final` | `8717e1f` | Ancestor; zero unique commits; empty `git cherry` | **Already contained.** |
| `agent/windows-installer-impl` | `8717e1f` | Ancestor; zero unique commits; empty `git cherry` | **Already contained.** |
| `agent/windows-installer-pr` | `8717e1f` | Ancestor; zero unique commits; empty `git cherry` | **Already contained.** |
| `agent/windows-installer-work` | `8717e1f` | Ancestor; zero unique commits; empty `git cherry` | **Already contained.** |
| `fix/preserve-legacy-settings` | `eaf8fc5` | `+ bdf5a0f` avoid deleting source when target exists; `+ eaf8fc5` regression | **Carry behavior, not whole branch**, through migration owner. Confirmed defect on main in `auth._migrate_from_source`; also review atomicity/error handling. |
| `fix/preserve-legacy-autostart` | `32861dd` | `+ 06f509b` retain legacy when target exists; `+ 32861dd` regression | **Carry behavior**, through migration owner. Main deletes legacy on name collision even without verifying replacement. Installer review does not edit `autostart.py`. |
| `fix/issue-9-network-settings-migration` | `2ded08b` | `+ 3ac15ac` preserve legacy when target exists; `+ 2ded08b` regression | **Carry behavior**, through migration owner. `net_utils` has the same source-deletion bug; network settings share `settings.json`, not a separate network file. |

The five `8717e1f` refs actually point to “1.4.1 fix session sync, power actions, pinned storage, launch args”; its changed files are apps/main/tests/web, not an unmerged installer implementation.

## Why main wins for packaging

Main's `f08ae47` introduced the current installer/release flow. Subsequent commits add testable manual packaging (`9e94816`), unattended install/ARP checks and distribution metadata (`c1cf623`), reliable exit-code capture (`019bbc7`), correct ARP display-name check (`ee1bf96`), and approved WinGet schema (`d728079`). The build helper proposed in `7b493f4` is unnecessary for this workflow.

Keep these contracts:

- Main AppId `{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}` and corresponding `_is1` ARP key. The experimental installer used **different** AppId `{B0D5BE86-E060-4F59-AE9C-78C0E67B4A9D}`. Replacing main's identity breaks upgrade/metadata continuity. Installing an experimental package is not evidence of upgrading the supported package.
- `PrivilegesRequired=lowest`, default `%LOCALAPPDATA%\Programs\PC Remote`, no permission override, current-user shortcuts.
- Version supplied with `/DAppVersion=...`, versioned filenames under `release`, main publisher/URL/icon metadata. Old helper hard-codes version `1.4.1` and writes `dist/installer/PC-Remote-Setup-x64.exe`.
- Silent installs do not launch the app; autostart is a user opt-in managed by the app, not a checked-by-default installer task.
- Preserve `%APPDATA%\PC Remote` and legacy settings directories on install, upgrade and uninstall.

## Firewall and service boundary

`9bdebd2` switches to `{autopf}` / administrator privileges and runs shell-wrapped netsh delete/add commands for `PC Remote LAN`. `69964a1` brings that behavior into the autostart branch. The rules apply on private/domain profiles; they are machine rules, not current-user rules. Deleting by a display name alone cannot establish ownership and can remove an unrelated/pre-existing rule. The installer also does not establish robust command-success verification.

**Do not port those commands.** Main neither installs a service nor creates a firewall rule, so the supported lifecycle should leave machine configuration unchanged. The smoke matrix compares service definitions and firewall rule/application-filter inventories before/after. It never adds/removes a service or firewall rule itself.

This does **not** promise cleanup of experimental admin packages, manually created rules, or rules Windows may create after a person approves a firewall prompt. Removing such state requires a separately authorized, ownership-aware administrative procedure. Do not compensate by elevating the user installer or deleting all rules with matching names.

## Confirmed installer gap and narrowly adapted fix

On pinned main, `autostart.install()` creates an opt-in Startup file at runtime, outside Inno's tracked files. The installer has no uninstall event, uninstall delete section or application cleanup invocation. Consequently uninstall can leave an entry pointing to a deleted EXE. This is a confirmed source-level gap, not a claim based on executing an installer here.

`installer/PC-Remote.iss` now removes only:

- `PC Remote.cmd` / `PC-Android.cmd` whose complete UTF-8 contents match the app-generated command targeting **this** `{app}\PC Remote.exe`;
- the `PC Remote` HKCU Run value, only when it exactly equals the quoted EXE path of this installation (compatibility with the experimental Run-key installer).

Startup comparison accepts the generated CRLF form and the historical CRCRLF form: Windows `Path.write_text` with default newline conversion doubles an explicitly supplied CRLF. A temporary-file Python check confirmed `b'@echo off\r\r\n'` on the review host. No real Startup file was written.

Unrelated/portable/source/customized entries are preserved; no wildcard deletion, current-user settings removal, runtime app launch during uninstall, forced opt-in, service action or firewall action was added. Failed owned-entry deletion is logged; VM residue assertions must still pass before lifecycle sign-off. Exact ownership matching intentionally prefers leaving an unrecognized entry over deleting someone else's.

## Verification and remaining gates

See [installer smoke matrix](docs/installer-smoke.md). Static contract tests first failed on the missing uninstall event, then on absent historical-newline handling, and passed after the minimal changes. PowerShell harness tests exercise **plan-only** output and denial when either explicit consent gate is absent. They do not execute the lifecycle.

The Inno compiler is not installed (not on PATH; neither standard Inno Setup 6 location exists), and `dist/PC Remote/PC Remote.exe` is absent. **Compilation, real upgrade, login autostart, and Windows uninstall residue are unverified.** No setup/uninstaller, service/firewall change or real autostart operation was run on this workstation. Do not label static or gate tests as real Windows lifecycle evidence.

Migration implementation belongs to the parallel migration task; its final changes and test results must be reviewed separately. No bulk import is recommended for any remaining branch.
