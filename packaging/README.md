# Distribution packaging

This directory documents the publication path for PC Remote. The goal is to keep distribution free for users and avoid paid signing or store fees wherever possible.

The release workflow generates ready-to-submit WinGet, Chocolatey, and Scoop metadata from the exact hashes of the release artifacts. Do not hand-edit hashes after release; regenerate the metadata from the release artifacts instead.

## 1. WinGet

Target repository: `microsoft/winget-pkgs`.

PC Remote is compatible with the community repository because the release uses a normal `.exe` Inno Setup installer, supports unattended installation, and has a stable version-specific GitHub release URL.

Prepared package identifier:

```text
mimaxon1.PCRemote
```

Generated folder layout:

```text
winget/manifests/m/mimaxon1/PCRemote/<version>/
  mimaxon1.PCRemote.yaml
  mimaxon1.PCRemote.installer.yaml
  mimaxon1.PCRemote.locale.en-US.yaml
  mimaxon1.PCRemote.locale.ru-RU.yaml
```

Important submission requirements checked against the current community-repository rules:

- Multi-file manifests are required; singleton manifests are not accepted.
- Every manifest must include the matching schema header.
- Use the newest manifest schema supported by the repository. The generator currently targets 1.28.0.
- A version-specific official HTTPS installer URL is used.
- SHA-256 is required and is generated from the actual release installer.
- The installer must install without user interaction. Inno Setup provides standard silent modes.
- One PR must contain one package version only.
- The manifest should be validated and the install tested before submission.

Recommended final validation on Windows:

```powershell
winget validate --manifest .\winget\manifests\m\mimaxon1\PCRemote\1.5.0
winget settings --enable LocalManifestFiles
winget install --manifest .\winget\manifests\m\mimaxon1\PCRemote\1.5.0
```

For a first contribution, Microsoft may ask the GitHub account to complete the Microsoft Contributor License Agreement. There is no package listing fee.

## 2. Chocolatey Community Repository

Prepared package id:

```text
pc-remote
```

The generated Chocolatey package does not embed the PC Remote executable. It downloads the official version-specific Setup EXE from GitHub Releases and verifies the SHA-256 hash. Because no application binary is bundled inside the `.nupkg`, a `VERIFICATION.txt` for bundled binaries is not needed.

The package includes the required project URL, description, license URL, copyright, source URL, bug tracker and silent installer arguments.

Build and test after a release:

```powershell
cd release\distribution\chocolatey
choco pack pc-remote.nuspec
choco install pc-remote --source . -y
```

Publication requires a Chocolatey Community account and its API key, but the community-package submission itself does not require a paid commercial Chocolatey license.

Typical publish command:

```powershell
choco push pc-remote.<version>.nupkg --source https://push.chocolatey.org/
```

Chocolatey moderation verifies that the package installs and uninstalls correctly, supports silent installation, has appropriate dependencies, and passes validator/scanner checks. The verifier currently runs on a Windows Server test environment, so a package can be rejected if the application itself is incompatible with that environment even when the metadata is correct.

## 3. Scoop

PC Remote is a GUI app, so it does **not** fit Scoop's `main` bucket criteria. `main` is intended for reasonably popular non-GUI developer tools. The correct upstream target is the **Extras** bucket.

The generated Scoop manifest intentionally uses the portable ZIP rather than the Setup EXE. This fits Scoop's preferred portable-app model and avoids registry/install side effects.

Generated file:

```text
scoop/pc-remote.json
```

Local test:

```powershell
scoop install .\release\distribution\scoop\pc-remote.json
```

The manifest contains GitHub-based `checkver` and `autoupdate` metadata, so future release updates can be automated by Scoop's tooling.

## 4. Microsoft Store

There are two Windows Store paths, but only one matches the project's zero-cost goal.

### EXE/MSI route — not recommended here

The Store accepts traditional EXE/MSI installers, but they and all PE files must already be Authenticode-signed with a certificate chaining to a CA in the Microsoft Trusted Root Program. Microsoft does not re-sign EXE/MSI submissions. That introduces a code-signing cost, so this route is intentionally not the target for PC Remote.

### MSIX route — preferred zero-cost route

Microsoft currently provides free developer registration in the new Partner Center onboarding flow and automatically re-signs Store-submitted MSIX/AppX packages after certification. A CA-trusted signing certificate is therefore not required for an MSIX submitted through the Store.

The repository includes an MSIX build helper and manifest template, but three identity values cannot be known before a Partner Center product is created:

- Package/Identity Name
- Publisher identity string
- Publisher display name

These must be copied exactly from Partner Center after reserving the product. Do not invent them: Store package identity is case-sensitive and must match the reserved product.

For a normal MSIX listing, a description and at least one real screenshot are required. Four or more screenshots are recommended. Store-specific listing logos are optional for normal MSIX apps, although a 300 x 300 app tile icon is recommended; the Store can fall back to the icon inside the package.

The Partner Center submission flow also requires pricing/availability, category/properties, age-rating information, package information, applicable license terms, and other product metadata. A privacy-policy URL is required when an app collects or transmits personal information; PC Remote includes `PRIVACY.md` regardless, so a public policy URL is available.

Before Store submission, build the MSIX with the Partner Center identity, install/test it, and run the Windows App Certification Kit.

## Release automation

`.github/workflows/release.yml` performs the application build and computes the release hashes. It then calls:

```powershell
python scripts/render_distribution.py `
  --version <version> `
  --setup-sha256 <sha256> `
  --portable-sha256 <sha256> `
  --output release/distribution
```

The generated metadata is uploaded as a GitHub Actions artifact together with the release build. Chocolatey's `.nupkg` is also built from the generated package without changing application code.

## What still requires an external account/action

The repository can prepare all package files, but final publication still requires the appropriate service account and its own review flow:

- WinGet: GitHub PR to `microsoft/winget-pkgs` and any required CLA confirmation.
- Chocolatey: Community account/API key and moderation.
- Scoop Extras: GitHub PR to `ScoopInstaller/Extras`.
- Microsoft Store: Partner Center onboarding, identity verification, product-name reservation, Store identity values, at least one real screenshot, and certification.

Do not bypass identity, eligibility, moderation, signing, or certification requirements. Use the official publisher workflows for each service.
