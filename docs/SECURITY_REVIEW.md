# Defensive security review

Reviewed base: `d728079` (current main at clone time). Source review and safe unit contracts only; no active exploitation, remote commands, power actions or real installation changes.

| Boundary | Source evidence on base | Classification / disposition |
|---|---|---|
| LAN transport | config.py API_HOST/WEB_HOST; README security model | Intentional all-interface HTTP. Document trusted-LAN-only restriction; no false claim of TLS or internet safety. |
| PIN authorization | main.py check() and change_password() call verify_password directly; only login() accounts failed attempts | Confirmed missing attempt budget on alternate PIN authorization paths. Shared legacy budget added with serialized admission/verify/accounting (lock), preserving PIN compatibility; token traffic unaffected. |
| Browser request execution | main.py CORSMiddleware; pair token issuance loopback-only; unauthenticated restart loopback-only, authenticated remote restart supported | Confirmed CORS-only browser boundary: CORS response restrictions do not reject all cross-origin execution. Explicit Origin rejection added before handlers. No-Origin native/tray clients still supported. |
| Peer identity | main.py run_api() leaves Uvicorn proxy_headers default; local-only access depends on request.client | Hardening: explicitly disable forwarded-header trust for this direct-LAN server. No configurable trusted reverse proxy is supported. |
| Settings migration | auth.py _migrate_from_source deletes source when destination exists and swallows copy errors | Confirmed data-integrity problem; addressed in migration workstream. |
| Autostart lifecycle | autostart.py writes per-user Startup CMD; installer lacks cleanup | Confirmed lifecycle gap; addressed in installer workstream, tested without changing this workstation. |
| Command launch | apps.py executable validation, start helpers, subprocess argv with shell=False; main.py launch endpoint authorization | By-design broad authenticated desktop control, not a sandbox. No claim that extension checks prevent a trusted client invoking an interpreter. Do not run elevated. |
| Restart | main.py _powershell_quote/_spawn_restart_watcher | Commands originate locally and strings use single-quote escaping. No remote command-string injection confirmed by this review. |
| Updates | installer AppUpdatesURL; build_release.py and release workflow | No runtime updater. Checksums and source-host trust documented; no signing guarantee. Reset requires explicit flag; retained unchanged. |
| Diagnostic privacy | new diagnostics.py | Output allowlist and bounded log scan; error category only. No PIN/hash/token/raw message export. Config path may identify OS account: review before sharing. |

## Verification

Baseline: 107 passed on Python 3.13.14; current full suite 130 passed.
Defensive contracts in `tests/test_security_contract.py` cover guard-before-hash,
failure accounting, success reset, token bypass, explicit Origin policy and
disabled proxy headers. Migration contracts in `tests/test_migration.py` cover
non-destructive legacy settings/autostart migration and exact CRLF bytes.
No working exploitation payload or vulnerability reproduction is included.

## Remaining limitations

Four-digit PIN entropy, plaintext transport, global legacy lockout availability,
trust of same-user local processes and broad authorized program launching remain
explicit design limitations. Origin policy is not authentication and is not a
network firewall. No pentest, VM install lifecycle, signature verification, or
remote reachability test has been performed by this review.
