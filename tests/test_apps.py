"""Unit tests for application discovery helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import apps


class TestListRecent:
    def test_list_recent_combines_running_and_shortcut_apps(self, tmp_path: Path):
        discord = tmp_path / "Discord.exe"
        telegram = tmp_path / "Telegram.exe"
        discord.write_text("", encoding="utf-8")
        telegram.write_text("", encoding="utf-8")

        running = [
            {"name": "Discord", "path": str(discord), "last_opened": 200.0},
        ]
        shortcuts = [
            {"name": "Telegram", "path": str(telegram), "last_opened": 100.0},
            {"name": "Discord", "path": str(discord), "last_opened": 50.0},
        ]

        with patch("apps._list_running_apps", return_value=running), patch("apps._list_shortcut_apps", return_value=shortcuts):
            result = apps.list_recent(limit=12)

        assert result == [
            {"name": "Discord", "path": str(discord)},
            {"name": "Telegram", "path": str(telegram)},
        ]

    def test_list_recent_prioritizes_explicit_path(self, tmp_path: Path):
        target = tmp_path / "Notion.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps._list_running_apps", return_value=[]), patch("apps._list_shortcut_apps", return_value=[]):
            result = apps.list_recent(limit=12, prioritized_paths=[str(target)])

        assert result == [{"name": "Notion", "path": str(target)}]

    def test_list_recent_filters_out_non_user_processes(self, tmp_path: Path):
        good = tmp_path / "Telegram.exe"
        bad = tmp_path / "SearchFilterHost.exe"
        good.write_text("", encoding="utf-8")
        bad.write_text("", encoding="utf-8")

        with patch("apps._list_running_apps", return_value=[]), patch(
            "apps._list_shortcut_apps",
            return_value=[
                {"name": "SearchFilterHost", "path": str(bad), "last_opened": 200.0},
                {"name": "Telegram", "path": str(good), "last_opened": 100.0},
            ],
        ):
            result = apps.list_recent(limit=12)

        assert result == [{"name": "Telegram", "path": str(good)}]

    def test_list_recent_filters_out_powertoys(self, tmp_path: Path):
        good = tmp_path / "Discord.exe"
        bad = tmp_path / "PowerToys.QuickAccess.exe"
        good.write_text("", encoding="utf-8")
        bad.write_text("", encoding="utf-8")

        with patch("apps._list_running_apps", return_value=[]), patch(
            "apps._list_shortcut_apps",
            return_value=[
                {"name": "PowerToys.QuickAccess", "path": str(bad), "last_opened": 200.0},
                {"name": "Discord", "path": str(good), "last_opened": 100.0},
            ],
        ):
            result = apps.list_recent(limit=12)

        assert result == [{"name": "Discord", "path": str(good)}]

    def test_list_recent_keeps_distinct_shortcuts_for_same_executable(self, tmp_path: Path):
        target = tmp_path / "chrome.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps._list_running_apps", return_value=[]), patch(
            "apps._list_shortcut_apps",
            return_value=[
                {"name": "Telegram", "path": str(target), "args": "--app-id=telegram", "last_opened": 200.0},
                {"name": "Excel", "path": str(target), "args": "--app-id=excel", "last_opened": 100.0},
            ],
        ):
            result = apps.list_recent(limit=12)

        assert result == [
            {"name": "Telegram", "path": str(target), "args": "--app-id=telegram"},
            {"name": "Excel", "path": str(target), "args": "--app-id=excel"},
        ]


class TestStart:
    def test_start_without_path_uses_first_recent_app(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps.list_recent", return_value=[{"name": "Telegram", "path": str(target)}]), patch("apps.subprocess.Popen") as mock_popen:
            result = apps.start()

        mock_popen.assert_called_once_with([str(target)], shell=False)
        assert result == {"name": "Telegram", "path": str(target)}

    def test_start_restores_existing_window_before_launching(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps._control_existing_window", return_value=True) as mock_control, patch("apps.subprocess.Popen") as mock_popen:
            result = apps.start(str(target))

        mock_control.assert_called_once_with({"name": "Telegram", "path": str(target)}, "activate")
        mock_popen.assert_not_called()
        assert result == {"name": "Telegram", "path": str(target)}

    def test_start_windowsapps_executable_uses_packaged_launcher(self):
        target = Path(
            r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_10.1906.55.0_x64__8wekyb3d8bbwe\Calculator.exe"
        )

        with patch("apps._validate_executable_path", return_value=target), patch("apps._start_packaged_app", return_value=True) as mock_packaged_start, patch("apps.subprocess.Popen") as mock_popen:
            result = apps.start(str(target))

        mock_packaged_start.assert_called_once_with(target)
        mock_popen.assert_not_called()
        assert result == {"name": "Calculator", "path": str(target)}

    def test_start_windowsapps_executable_raises_when_packaged_launcher_fails(self):
        target = Path(
            r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_10.1906.55.0_x64__8wekyb3d8bbwe\Calculator.exe"
        )

        with patch("apps._validate_executable_path", return_value=target), patch("apps._start_packaged_app", return_value=False), patch("apps.subprocess.Popen") as mock_popen:
            try:
                apps.start(str(target))
            except RuntimeError as exc:
                assert str(exc) == "failed to start application"
            else:
                raise AssertionError("RuntimeError was not raised")

        mock_popen.assert_not_called()

    def test_start_rejects_non_user_processes(self, tmp_path: Path):
        target = tmp_path / "RuntimeBroker.exe"
        target.write_text("", encoding="utf-8")

        try:
            apps.start(str(target))
        except ValueError as exc:
            assert str(exc) == "application is not suitable for quick launch"
        else:
            raise AssertionError("ValueError was not raised")

    def test_start_uses_arguments_for_shortcut_launches(self, tmp_path: Path):
        target = tmp_path / "chrome.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps.os.startfile") as mock_startfile:
            result = apps.start(str(target), name="Telegram", args="--app-id=telegram")

        mock_startfile.assert_called_once_with(str(target), arguments="--app-id=telegram")
        assert result == {
            "name": "Telegram",
            "path": str(target),
            "args": "--app-id=telegram",
        }

    def test_start_accepts_quoted_executable_path(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps.subprocess.Popen") as mock_popen:
            result = apps.start(f'"{target}"')

        mock_popen.assert_called_once_with([str(target)], shell=False)
        assert result == {"name": "Telegram", "path": str(target)}

    def test_window_action_minimizes_existing_window(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps._control_existing_window", return_value=True) as mock_control:
            result = apps.window_action("minimize", str(target))

        mock_control.assert_called_once_with({"name": "Telegram", "path": str(target)}, "minimize")
        assert result == {"name": "Telegram", "path": str(target)}

    def test_window_action_raises_when_window_not_found(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps._control_existing_window", return_value=False):
            try:
                apps.window_action("close", str(target))
            except ValueError as exc:
                assert str(exc) == "application window not found"
            else:
                raise AssertionError("ValueError was not raised")


class TestPinnedApps:
    def test_pin_persists_apps_and_moves_latest_to_front(self, tmp_path: Path):
        telegram = tmp_path / "Telegram.exe"
        discord = tmp_path / "Discord.exe"
        telegram.write_text("", encoding="utf-8")
        discord.write_text("", encoding="utf-8")

        with patch("apps.config.app_dir", return_value=tmp_path):
            first = apps.pin(str(telegram))
            second = apps.pin(str(discord))
            result = apps.list_pinned()

        assert first == {"name": "Telegram", "path": str(telegram)}
        assert second == {"name": "Discord", "path": str(discord)}
        assert result == [
            {"name": "Discord", "path": str(discord)},
            {"name": "Telegram", "path": str(telegram)},
        ]

    def test_unpin_removes_saved_app(self, tmp_path: Path):
        target = tmp_path / "Notion.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps.config.app_dir", return_value=tmp_path):
            apps.pin(str(target))
            removed = apps.unpin(str(target))
            result = apps.list_pinned()

        assert removed is True
        assert result == []

    def test_pin_deduplicates_path_variants_for_same_app(self, tmp_path: Path):
        target = tmp_path / "Telegram.exe"
        target.write_text("", encoding="utf-8")
        variant_path = str(target).replace("\\", "/")
        variant = f'"{variant_path}"'

        with patch("apps.config.app_dir", return_value=tmp_path):
            first = apps.pin(str(target))
            second = apps.pin(variant)
            result = apps.list_pinned()

        assert first == {"name": "Telegram", "path": str(target)}
        assert second == {"name": "Telegram", "path": str(target)}
        assert result == [{"name": "Telegram", "path": str(target)}]

    def test_pin_rejects_non_user_processes(self, tmp_path: Path):
        target = tmp_path / "WireguardService.exe"
        target.write_text("", encoding="utf-8")

        with patch("apps.config.app_dir", return_value=tmp_path):
            try:
                apps.pin(str(target))
            except ValueError as exc:
                assert str(exc) == "application is not suitable for quick launch"
            else:
                raise AssertionError("ValueError was not raised")

    def test_list_pinned_ignores_missing_or_invalid_entries(self, tmp_path: Path):
        existing = tmp_path / "Firefox.exe"
        existing.write_text("", encoding="utf-8")
        storage = tmp_path / "pinned_apps.json"
        storage.write_text(
            """
[
  {"name": "Firefox", "path": "%s"},
  {"name": "Missing", "path": "%s"},
  {"name": "Text", "path": "%s"}
]
""".strip()
            % (
                str(existing).replace("\\", "\\\\"),
                str(tmp_path / "Missing.exe").replace("\\", "\\\\"),
                str(tmp_path / "notes.txt").replace("\\", "\\\\"),
            ),
            encoding="utf-8",
        )

        with patch("apps.config.app_dir", return_value=tmp_path):
            result = apps.list_pinned()

        assert result == [{"name": "Firefox", "path": str(existing)}]
