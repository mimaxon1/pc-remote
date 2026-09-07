#!/usr/bin/env python3
"""Render distribution metadata for a PC Remote release.

This script intentionally does not publish anything. It creates ready-to-submit
metadata for WinGet, Chocolatey, and Scoop using hashes from the already-built
release artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from textwrap import dedent
from xml.sax.saxutils import escape

REPO = "https://github.com/mimaxon1/pc-remote"
PACKAGE_ID = "mimaxon1.PCRemote"
CHOCO_ID = "pc-remote"
PRODUCT_CODE = "8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4_is1"
WINGET_SCHEMA = "1.28.0"


def _hash(value: str, name: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    return value.upper()


def _version(value: str) -> str:
    value = value.strip().removeprefix("v")
    if not value or any(ch in value for ch in "\\/\r\n\t"):
        raise ValueError("invalid version")
    return value


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def render_winget(root: Path, version: str, setup_sha: str) -> None:
    base = root / "winget" / "manifests" / "m" / "mimaxon1" / "PCRemote" / version
    setup_url = (
        f"{REPO}/releases/download/v{version}/"
        f"PC-Remote-{version}-windows-x64-Setup.exe"
    )

    _write(
        base / f"{PACKAGE_ID}.yaml",
        dedent(
            f"""\
            # yaml-language-server: $schema=https://aka.ms/winget-manifest.version.{WINGET_SCHEMA}.schema.json
            PackageIdentifier: {PACKAGE_ID}
            PackageVersion: '{version}'
            DefaultLocale: en-US
            ManifestType: version
            ManifestVersion: {WINGET_SCHEMA}
            """
        ),
    )

    _write(
        base / f"{PACKAGE_ID}.installer.yaml",
        dedent(
            f"""\
            # yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.{WINGET_SCHEMA}.schema.json
            PackageIdentifier: {PACKAGE_ID}
            PackageVersion: '{version}'
            InstallerType: inno
            Scope: user
            InstallModes:
              - interactive
              - silent
              - silentWithProgress
            UpgradeBehavior: install
            ProductCode: {PRODUCT_CODE}
            Installers:
              - Architecture: x64
                InstallerUrl: {setup_url}
                InstallerSha256: {setup_sha}
                AppsAndFeaturesEntries:
                  - DisplayName: PC Remote
                    Publisher: mimaxon1
                    DisplayVersion: '{version}'
                    ProductCode: {PRODUCT_CODE}
                InstallationMetadata:
                  DefaultInstallLocation: '%LocalAppData%\\Programs\\PC Remote'
            ManifestType: installer
            ManifestVersion: {WINGET_SCHEMA}
            """
        ),
    )

    _write(
        base / f"{PACKAGE_ID}.locale.en-US.yaml",
        dedent(
            f"""\
            # yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.{WINGET_SCHEMA}.schema.json
            PackageIdentifier: {PACKAGE_ID}
            PackageVersion: '{version}'
            PackageLocale: en-US
            Publisher: mimaxon1
            PublisherUrl: {REPO}
            PublisherSupportUrl: {REPO}/issues
            Author: mimaxon1
            PackageName: PC Remote
            PackageUrl: {REPO}
            License: Apache-2.0
            LicenseUrl: {REPO}/blob/main/LICENSE
            Copyright: Copyright 2026 mimaxon1
            ShortDescription: Control a Windows PC from any phone browser over the local network.
            Description: >-
              PC Remote is an open-source, local-first Windows remote controller.
              Run it on the PC, pair a phone with a QR code, and control apps,
              windows, media, audio output, volume, and power actions from a browser.
              No mobile app, cloud service, or external account is required.
            Moniker: pc-remote
            Tags:
              - lan
              - local-first
              - media-control
              - phone-remote
              - remote-control
              - self-hosted
              - windows
            ReleaseNotesUrl: {REPO}/releases/tag/v{version}
            ManifestType: defaultLocale
            ManifestVersion: {WINGET_SCHEMA}
            """
        ),
    )

    _write(
        base / f"{PACKAGE_ID}.locale.ru-RU.yaml",
        dedent(
            f"""\
            # yaml-language-server: $schema=https://aka.ms/winget-manifest.locale.{WINGET_SCHEMA}.schema.json
            PackageIdentifier: {PACKAGE_ID}
            PackageVersion: '{version}'
            PackageLocale: ru-RU
            Publisher: mimaxon1
            PackageName: PC Remote
            ShortDescription: Управление Windows-компьютером с телефона через локальную сеть.
            Description: >-
              PC Remote — локальный open-source пульт для Windows.
              Запустите приложение на ПК, подключите телефон по QR-коду и управляйте
              приложениями, окнами, мультимедиа, аудио, громкостью и питанием из браузера.
              Мобильное приложение, облако и внешний аккаунт не требуются.
            ManifestType: locale
            ManifestVersion: {WINGET_SCHEMA}
            """
        ),
    )


def render_chocolatey(root: Path, version: str, setup_sha: str) -> None:
    base = root / "chocolatey"
    setup_url = (
        f"{REPO}/releases/download/v{version}/"
        f"PC-Remote-{version}-windows-x64-Setup.exe"
    )

    description = (
        "PC Remote is a free, open-source Windows remote controller that lets you "
        "control apps, windows, media, audio, volume, and power actions from any "
        "phone browser on the same local network. It does not require a mobile app, "
        "cloud service, or external account."
    )

    _write(
        base / f"{CHOCO_ID}.nuspec",
        dedent(
            f"""\
            <?xml version="1.0" encoding="utf-8"?>
            <package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">
              <metadata>
                <id>{CHOCO_ID}</id>
                <version>{escape(version)}</version>
                <title>PC Remote</title>
                <authors>mimaxon1</authors>
                <owners>mimaxon1</owners>
                <projectUrl>{REPO}</projectUrl>
                <packageSourceUrl>{REPO}</packageSourceUrl>
                <projectSourceUrl>{REPO}</projectSourceUrl>
                <bugTrackerUrl>{REPO}/issues</bugTrackerUrl>
                <licenseUrl>{REPO}/blob/main/LICENSE</licenseUrl>
                <requireLicenseAcceptance>false</requireLicenseAcceptance>
                <copyright>Copyright 2026 mimaxon1</copyright>
                <summary>Control a Windows PC from any phone browser over the local network.</summary>
                <description>{escape(description)}</description>
                <releaseNotes>{REPO}/releases/tag/v{escape(version)}</releaseNotes>
                <tags>pc-remote remote-control windows lan local-first self-hosted media-control phone-remote</tags>
              </metadata>
              <files>
                <file src="tools\\**" target="tools" />
              </files>
            </package>
            """
        ),
    )

    _write(
        base / "tools" / "chocolateyinstall.ps1",
        dedent(
            f"""\
            $ErrorActionPreference = 'Stop'

            if (-not [Environment]::Is64BitOperatingSystem) {{
              throw 'PC Remote requires 64-bit Windows.'
            }}

            $packageArgs = @{{
              packageName    = '{CHOCO_ID}'
              fileType       = 'exe'
              url64bit       = '{setup_url}'
              checksum64     = '{setup_sha}'
              checksumType64 = 'sha256'
              silentArgs     = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'
              validExitCodes = @(0)
            }}

            Install-ChocolateyPackage @packageArgs
            """
        ),
    )


def render_scoop(root: Path, version: str, portable_sha: str) -> None:
    import json

    portable_url = (
        f"{REPO}/releases/download/v{version}/"
        f"PC-Remote-{version}-windows-x64-portable.zip"
    )
    manifest = {
        "version": version,
        "description": (
            "Control a Windows PC from any phone browser over the local network. "
            "No mobile app, account, or cloud service required."
        ),
        "homepage": REPO,
        "license": "Apache-2.0",
        "architecture": {
            "64bit": {
                "url": portable_url,
                "hash": portable_sha.lower(),
            }
        },
        "extract_dir": "PC Remote",
        "shortcuts": [["PC Remote.exe", "PC Remote"]],
        "checkver": {"github": REPO},
        "autoupdate": {
            "architecture": {
                "64bit": {
                    "url": (
                        f"{REPO}/releases/download/v$version/"
                        "PC-Remote-$version-windows-x64-portable.zip"
                    )
                }
            }
        },
    }
    _write(root / "scoop" / "pc-remote.json", json.dumps(manifest, indent=4, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--setup-sha256", required=True)
    parser.add_argument("--portable-sha256", required=True)
    parser.add_argument("--output", default="release/distribution")
    args = parser.parse_args()

    version = _version(args.version)
    setup_sha = _hash(args.setup_sha256, "setup SHA-256")
    portable_sha = _hash(args.portable_sha256, "portable SHA-256")
    root = Path(args.output)

    render_winget(root, version, setup_sha)
    render_chocolatey(root, version, setup_sha)
    render_scoop(root, version, portable_sha)

    marker = root / "GENERATED.txt"
    digest = hashlib.sha256(
        f"{version}|{setup_sha}|{portable_sha}".encode("utf-8")
    ).hexdigest()
    _write(
        marker,
        f"Generated for PC Remote v{version}\nInputs digest: {digest}\n",
    )
    print(f"distribution metadata written to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
