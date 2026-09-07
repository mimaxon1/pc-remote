from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def test_distribution_renderer_generates_all_package_formats(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "render_distribution.py"
    out = tmp_path / "distribution"
    setup_sha = "a" * 64
    portable_sha = "b" * 64

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--version",
            "1.5.0",
            "--setup-sha256",
            setup_sha,
            "--portable-sha256",
            portable_sha,
            "--output",
            str(out),
        ],
        cwd=repo,
        check=True,
    )

    winget = out / "winget" / "manifests" / "m" / "mimaxon1" / "PCRemote" / "1.5.0"
    assert {p.name for p in winget.iterdir()} == {
        "mimaxon1.PCRemote.yaml",
        "mimaxon1.PCRemote.installer.yaml",
        "mimaxon1.PCRemote.locale.en-US.yaml",
        "mimaxon1.PCRemote.locale.ru-RU.yaml",
    }

    installer = (winget / "mimaxon1.PCRemote.installer.yaml").read_text(encoding="utf-8")
    assert "ManifestVersion: 1.28.0" in installer
    assert "InstallerType: inno" in installer
    assert "Scope: user" in installer
    assert setup_sha.upper() in installer
    assert "PC-Remote-1.5.0-windows-x64-Setup.exe" in installer
    assert "'{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}_is1'" in installer

    nuspec = out / "chocolatey" / "pc-remote.nuspec"
    ET.parse(nuspec)
    chocolatey_install = (out / "chocolatey" / "tools" / "chocolateyinstall.ps1").read_text(
        encoding="utf-8"
    )
    assert "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-" in chocolatey_install
    assert setup_sha.upper() in chocolatey_install

    scoop = json.loads((out / "scoop" / "pc-remote.json").read_text(encoding="utf-8"))
    assert scoop["version"] == "1.5.0"
    assert scoop["architecture"]["64bit"]["hash"] == portable_sha
    assert scoop["extract_dir"] == "PC Remote"
    assert scoop["shortcuts"] == [["PC Remote.exe", "PC Remote"]]
    assert "$version" in scoop["autoupdate"]["architecture"]["64bit"]["url"]

    assert (out / "GENERATED.txt").is_file()


def test_store_manifest_template_is_well_formed_xml() -> None:
    repo = Path(__file__).resolve().parents[1]
    ET.parse(repo / "packaging" / "microsoft-store" / "Package.appxmanifest.template")
