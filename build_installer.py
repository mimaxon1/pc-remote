"""Build the portable PC Remote bundle and package it as a single Setup.exe."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ISS_FILE = ROOT / "installer" / "PC-Remote.iss"
DEFAULT_ISCC_CANDIDATES = (
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
)


def _find_iscc(explicit: str | None) -> Path | None:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None

    on_path = shutil.which("ISCC.exe") or shutil.which("iscc")
    if on_path:
        return Path(on_path)

    for candidate in DEFAULT_ISCC_CANDIDATES:
        if str(candidate) and candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build PC Remote and produce dist/installer/PC-Remote-Setup-x64.exe.",
    )
    parser.add_argument(
        "--iscc",
        help="Path to Inno Setup compiler (ISCC.exe). Auto-detected when omitted.",
    )
    parser.add_argument(
        "--skip-bundle",
        action="store_true",
        help="Skip PyInstaller and package the existing dist/PC Remote bundle.",
    )
    parser.add_argument(
        "--reset-settings",
        action="store_true",
        help="Pass --reset-settings to build_release.py before packaging.",
    )
    args = parser.parse_args(argv)

    if not args.skip_bundle:
        command = [sys.executable, str(ROOT / "build_release.py")]
        if args.reset_settings:
            command.append("--reset-settings")
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return int(completed.returncode)

    bundle_exe = ROOT / "dist" / "PC Remote" / "PC Remote.exe"
    if not bundle_exe.is_file():
        print(f"Portable bundle is missing: {bundle_exe}", file=sys.stderr)
        return 2

    iscc = _find_iscc(args.iscc)
    if iscc is None:
        print(
            "Inno Setup 6 was not found. Install it or pass --iscc C:\\...\\ISCC.exe.",
            file=sys.stderr,
        )
        return 3

    completed = subprocess.run([str(iscc), str(ISS_FILE)], cwd=ROOT, check=False)
    if completed.returncode:
        return int(completed.returncode)

    output = ROOT / "dist" / "installer" / "PC-Remote-Setup-x64.exe"
    print(f"installer: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
