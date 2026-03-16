"""Build helper for PyInstaller-based Windows bundles."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import config


def _settings_candidates() -> list[Path]:
    candidates: list[Path] = []

    appdata_dir = config.app_dir()
    candidates.append(appdata_dir / config.SETTINGS_FILENAME)

    base = config.appdata_base_dir()
    if base is not None:
        for legacy_name in config.LEGACY_APP_NAMES:
            candidates.append(base / legacy_name / config.SETTINGS_FILENAME)

    candidates.append(Path(__file__).resolve().parent / config.SETTINGS_FILENAME)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _remove_settings(paths: list[Path], dry_run: bool) -> list[str]:
    actions: list[str] = []
    for path in paths:
        if path.exists():
            if dry_run:
                actions.append(f"would remove {path}")
                continue
            path.unlink()
            actions.append(f"removed {path}")
            parent = path.parent
            try:
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass
        else:
            actions.append(f"missing {path}")
    return actions


def _build_command(pyinstaller_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "PC-Remote.spec",
        "--clean",
        "-y",
        *pyinstaller_args,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Windows bundle and optionally reset persisted settings first.",
    )
    parser.add_argument(
        "--reset-settings",
        action="store_true",
        help="Remove persisted app settings before building.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed and which build command would run.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Only reset persisted settings, do not invoke PyInstaller.",
    )
    args, pyinstaller_args = parser.parse_known_args(argv)

    if args.reset_settings:
        actions = _remove_settings(_settings_candidates(), dry_run=args.dry_run)
        for action in actions:
            print(action)
    else:
        print("preserving persisted settings (use --reset-settings to remove them before build)")

    if args.skip_build:
        return 0

    command = _build_command(pyinstaller_args)
    print("build command:", subprocess.list2cmdline(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
