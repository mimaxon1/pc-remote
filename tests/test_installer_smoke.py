"""Safety checks for the optional disposable-VM script; never execute it here."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "installer_smoke.ps1"


def test_vm_smoke_is_an_explicit_opt_in():
    assert SCRIPT.is_file(), "Disposable-VM installer smoke harness is missing"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$Execute" in text
    assert "PC_REMOTE_DISPOSABLE_VM" in text
    assert "I_ACCEPT_DISPOSABLE_VM" in text
    assert text.index("if (-not $Execute)") < text.index("Start-Process")
    assert "IsInRole" in text  # reject elevated context


def test_lifecycle_checks_legacy_choice_and_process_residue():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Upgrade modified legacy autostart choice." in text
    assert "Uninstall left running application." in text
    assert "New-Item -Path $runKey -Force" not in text
    assert "if (-not (Test-Path $runKey))" in text


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell unavailable")
def test_default_vm_smoke_is_plan_only():
    assert SCRIPT.is_file(), "Disposable-VM installer smoke harness is missing"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "not_run"
    assert report["stages"] == ["fresh-install", "seed-settings-autostart", "upgrade", "uninstall"]


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell unavailable")
@pytest.mark.parametrize("confirmation,env_gate", [("", ""), ("I_ACCEPT_DISPOSABLE_VM", ""), ("", "1")])
def test_execute_is_rejected_without_both_consent_gates(confirmation, env_gate):
    # Deliberately never supply both: cannot reach OS-changing code.
    env = dict(os.environ, PC_REMOTE_DISPOSABLE_VM=env_gate)
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), "-Execute"]
    if confirmation:
        command += ["-Confirmation", confirmation]
    result = subprocess.run(command, env=env, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert b"Execution denied" in result.stderr
