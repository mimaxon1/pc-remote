"""Unit tests for tray GUI fallbacks."""

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
