"""Unit tests for tray GUI fallbacks."""

from collections import deque
import queue
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
        gui._tk_queue = queue.Queue()
        gui._tk_root = None

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

    def test_pair_url_uses_token_when_available(self):
        assert gui._pair_url("http://pc:8080", "pair-token") == "http://pc:8080/?token=pair-token"

    def test_pair_url_falls_back_to_base_url(self):
        assert gui._pair_url("http://pc:8080", None) == "http://pc:8080"

    def test_alternative_pair_urls_use_secondary_hosts(self):
        with patch("gui.net_utils.get_public_hosts", return_value=["wifi-host", "eth-host", "vpn-host"]):
            assert gui._alternative_pair_urls("pair-token") == [
                "http://eth-host:8080/?token=pair-token",
                "http://vpn-host:8080/?token=pair-token",
            ]

    def test_widget_exists_handles_destroyed_tk_root(self):
        class DestroyedRoot:
            def winfo_exists(self):
                raise gui.tk.TclError("application has been destroyed")

        assert gui._widget_exists(DestroyedRoot()) is False

    def test_process_tk_queue_ignores_destroyed_root(self):
        class DestroyedRoot:
            def winfo_exists(self):
                raise gui.tk.TclError("application has been destroyed")

        gui._tk_root = DestroyedRoot()
        gui._process_tk_queue()

    def test_request_exit_clears_dead_root_reference(self):
        class DeadRoot:
            def winfo_exists(self):
                raise gui.tk.TclError("application has been destroyed")

        gui._tk_root = DeadRoot()
        gui.request_exit()

        fn = gui._tk_queue.get_nowait()
        fn()

        assert gui._tk_root is None
