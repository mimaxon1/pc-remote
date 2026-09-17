# Security Policy

## Supported versions

Security fixes are provided on a best-effort basis for:

| Version | Supported |
| --- | --- |
| Latest `main` branch | Yes |
| Latest tagged release | Yes |
| Older releases | No |

## Reporting a vulnerability

Please do not publish vulnerability details in a regular GitHub issue.

Prefer GitHub Private Vulnerability Reporting for this repository. If private reporting is unavailable, open a minimal issue requesting a private contact channel without including exploit details, credentials, logs, or other sensitive information.

Useful information for a private report includes:

- affected version, branch, or commit
- environment details
- steps to reproduce
- expected and actual behavior
- impact assessment, if known
- relevant logs or proof of concept

## Scope note

PC Remote is designed for trusted local-network use. The default transport is plain HTTP and the application should not be exposed directly to the public internet.

## Runtime boundaries and residual risks

- Both servers bind all interfaces by default. Use only a trusted private LAN;
  guest Wi-Fi, port forwarding and direct internet exposure are unsupported.
  Plain HTTP does not protect PINs or session tokens from network observers.
- A paired client has the current Windows user's application-launch, window,
  media and power privileges. This is not a sandbox or a multi-user access-control
  system. Executable extension checks and `shell=False` are not an allowlist.
  Do not run PC Remote elevated; do not give untrusted people the PIN/QR token.
- PIN hashes are salted PBKDF2; tokens are random, short-lived and memory-only.
  A four-digit PIN still has low entropy. `/login` has a per-peer attempt budget;
  legacy action PINs and PIN changes share a separate global attempt budget.
  A malicious peer can temporarily exhaust that legacy budget; valid session
  tokens are not blocked by it. This is not a distributed-attack defence.
- API requests carrying a browser Origin must match the explicit local-origin
  list. CORS alone is not authorization. Requests without Origin remain supported
  for the local tray/native clients and must satisfy endpoint authorization.
  Pairing-token issuance is loopback-only; an unauthenticated restart is accepted
  only from loopback, while an authenticated remote restart remains supported.
  Local malware is outside this trust boundary. Uvicorn forwarded-client headers
  are disabled deliberately.
- Settings and logs are in user-writable AppData. They are not protected from
  another process running as the same Windows user. Diagnostics emits categories,
  never settings contents or raw log/error messages.

## Installation and updates

There is no in-app download-and-execute updater. Obtain releases from the project's
GitHub release page, and verify the published SHA-256 checksums before installing.
Checksums hosted with a release detect corruption, not compromise of the publisher.
The current distribution has no guaranteed Authenticode signing trust chain.
Installer user scope is intentional: no service or elevated firewall provisioning
is required. Do not import old elevated installer branches wholesale.

`build_release.py` preserves settings by default. `--reset-settings` and clean
restart explicitly delete settings; they are not upgrade/migration mechanisms.
Keep backups before intentional resets. An actual clean-install/upgrade/uninstall
claim requires the disposable-Windows smoke matrix, not just Python tests.

## Review evidence

See `docs/SECURITY_REVIEW.md`, `docs/diagnostics.md` and
`BRANCH_MIGRATION_REPORT.md`. Automated defensive tests do not constitute a
penetration test or guarantee that all vulnerabilities have been found.

## Disclosure

Please allow reasonable time to investigate and prepare a fix before publishing exploit details.
