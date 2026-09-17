"""Static Inno contracts, not proof of Windows install/uninstall behavior."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "PC-Remote.iss"


def test_uninstall_cleans_only_matching_current_user_autostart():
    source = ISS.read_text(encoding="utf-8")
    assert "procedure CurUninstallStepChanged" in source
    assert "usUninstall" in source
    assert "RemoveOwnedStartupFile('PC Remote.cmd')" in source
    assert "RemoveOwnedStartupFile('PC-Android.cmd')" in source
    # Remove only exact generated entries; never wildcard a user's Startup folder.
    assert "Content = UTF8Encode(Expected)" in source
    # Path.write_text(..., newline=None) on Windows translates explicit CRLF.
    assert "StringChangeEx(Expected, #13#10, #13#13#10, True)" in source
    assert "Command = Expected" in source
    assert "RegDeleteValue(HKCU" in source
    assert "DeleteFile(Filename)" in source


def test_user_scope_and_no_implicit_autostart_or_machine_changes():
    source = ISS.read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in source
    assert "DefaultDirName={localappdata}\\Programs\\{#MyAppName}" in source
    assert "AppId={{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}" in source
    assert "postinstall skipifsilent" in source
    for forbidden in ("PrivilegesRequiredOverridesAllowed", "[Registry]", "[UninstallDelete]",
                      "netsh", "HKLM", "sc.exe", "schtasks", "RegWrite"):
        assert forbidden not in source
    assert "settings.json" not in source
    assert "network_settings.json" not in source
