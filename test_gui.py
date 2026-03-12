"""Unit tests for tray GUI fallbacks."""

from collections import deque
from unittest.mock import patch

import gui


class TestTrayFallbacks:
    def test_tray_support_error_prefers_pystray(self):
        with patch.object(gui, "_PYSTRAY_AVAILABLE", False), patch.object(gui, "_PIL_AVAILABLE", False):
            assert gui._tray_support_error() == "pystray is not installed; tray UI disabled"

    def test_run_without_tray_keeps_gui_loop(self):
        with patch.object(gui, "_PYSTRAY_AVAILABLE", False), patch.object(gui, "_PIL_AVAILABLE", True):
            with patch("gui.add_log") as add_log, patch("gui.start_gui") as start_gui, patch("gui.start_tray") as start_tray:
                gui.run()

        start_gui.assert_called_once_with()
        start_tray.assert_not_called()
        assert add_log.call_count == 2


class TestGuiHelpers:
    def setup_method(self):
        gui.logs = deque(maxlen=gui.config.LOG_BUFFER_LIMIT)
        gui._next_log_id = 0
        gui._pair_waiters = {}

    def test_get_logs_supports_incremental_reads(self):
        gui.add_log("one")
        gui.add_log("two")
        gui.add_log("three")

        entries, next_since, reset = gui.get_logs(1, 10)

        assert [entry.message for entry in entries] == ["two", "three"]
        assert next_since == 3
        assert reset is False

    def test_notify_pair_completed_sets_waiter(self):
        waiter = gui.register_pair_waiter("pair-token")
        assert waiter is not None
        assert waiter.is_set() is False

        gui.notify_pair_completed("pair-token")

        assert waiter.is_set() is True
