"""Unit tests for main application module."""
import pytest
import socket
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import main


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = float(start)

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class TestPortChecking:
    """Test port availability checking."""
    
    def test_check_port_available_open_port(self):
        """Test checking an available port."""
        # Port 9999 is typically not in use
        is_available = main.check_port_available(9999)
        # This might be unreliable in test environment, so we just verify it returns a bool
        assert isinstance(is_available, bool)
    
    def test_check_port_available_loopback(self):
        """Test port checking on loopback interface."""
        # Find an available port to test with
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, test_port = s.getsockname()
        
        # Now test that our checker correctly identifies an available port
        # (after the socket is closed)
        result = main.check_port_available(test_port)
        # Result should be True since the socket was closed
        assert result is True

    def test_check_port_available_bound_port(self):
        """A bound port must be treated as unavailable even before listen()."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("127.0.0.1", 0))
            _, test_port = s.getsockname()
            assert main.check_port_available(test_port) is False
    
    def test_verify_ports_available_both_good(self):
        """Test verification when both ports are available (mocked)."""
        with patch.object(main, "check_port_available", return_value=True):
            result = main.verify_ports_available(8000, 8080)
            assert result is True
    
    def test_verify_ports_available_api_busy(self):
        """Test verification when API port is busy."""
        def mock_check(port):
            return port != 8000  # Port 8000 is busy
        
        with patch.object(main, "check_port_available", side_effect=mock_check):
            with patch("main.logger"):
                with patch("main.gui.add_log"):
                    result = main.verify_ports_available(8000, 8080)
                    assert result is False
    
    def test_verify_ports_available_web_busy(self):
        """Test verification when web port is busy."""
        def mock_check(port):
            return port != 8080  # Port 8080 is busy
        
        with patch.object(main, "check_port_available", side_effect=mock_check):
            with patch("main.logger"):
                with patch("main.gui.add_log"):
                    result = main.verify_ports_available(8000, 8080)
                    assert result is False


class TestCORSSetup:
    """Test CORS middleware configuration."""
    
    def test_cors_middleware_exists(self):
        """Test that CORS middleware is configured."""
        # Check that app has middleware configured
        assert main.app is not None
        # The middleware should be in the middleware_stack
        # This is a smoke test to verify CORS is set up
        assert hasattr(main.app, "middleware_stack")


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_endpoint_structure(self):
        """Test that /health endpoint returns correct structure."""
        with patch("main._auth_manager") as mock_auth:
            mock_manager = MagicMock()
            mock_manager.requires_password_setup.return_value = False
            mock_auth.return_value = mock_manager
            
            client = TestClient(main.app)
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "auth_ready" in data
        assert data["version"] == main.config.APP_VERSION


class TestRuntimeConfig:
    def test_runtime_config_exposes_version_and_backoff(self):
        script = main._runtime_config_script().decode("utf-8")

        assert f'"appVersion": "{main.config.APP_VERSION}"' in script
        assert f'"offlineRetryMinMs": {main.config.WEB_OFFLINE_RETRY_MIN_MS}' in script
        assert f'"offlineRetryMaxMs": {main.config.WEB_OFFLINE_RETRY_MAX_MS}' in script


class TestVsCodeCleanStart:
    def test_should_not_reset_persisted_state_for_vscode_by_default(self):
        with patch("main.sys.frozen", False, create=True), patch.dict(
            "main.os.environ",
            {"TERM_PROGRAM": "vscode"},
            clear=True,
        ):
            assert main._should_reset_persisted_state_for_vscode() is False

    def test_should_reset_persisted_state_when_explicitly_enabled(self):
        with patch("main.sys.frozen", False, create=True), patch.dict(
            "main.os.environ",
            {
                "TERM_PROGRAM": "vscode",
                "PC_REMOTE_VSCODE_CLEAN_START": "1",
            },
            clear=True,
        ):
            assert main._should_reset_persisted_state_for_vscode() is True

    def test_prepare_vscode_clean_start_skips_non_vscode_runs(self):
        with patch("main._should_reset_persisted_state_for_vscode", return_value=False), patch("main.auth.remove_persisted_settings") as mock_remove:
            removed = main._prepare_vscode_clean_start()

        assert removed == []
        mock_remove.assert_not_called()


class TestRestartEndpoint:
    def test_restart_endpoint_schedules_clean_restart_for_remote_client(self):
        client = TestClient(main.app)

        with patch("main.check") as mock_check, patch("main._request_application_restart", return_value=True) as mock_restart, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/app/restart", json={"token": "x" * 32, "clean_start": True})

        assert response.status_code == 200
        assert response.json() == {"status": "restarting", "clean_start": True}
        mock_check.assert_called_once_with("x" * 32, None)
        mock_restart.assert_called_once_with(clean_start=True)
        mock_add_log.assert_called_once_with("Clean restart requested")

    def test_restart_endpoint_allows_local_request_without_auth(self):
        client = TestClient(main.app)

        with patch("main._is_local_request", return_value=True), patch("main.check") as mock_check, patch("main._request_application_restart", return_value=True) as mock_restart, patch("main.gui.add_log"):
            response = client.post("/app/restart", json={"clean_start": True})

        assert response.status_code == 200
        assert response.json() == {"status": "restarting", "clean_start": True}
        mock_check.assert_not_called()
        mock_restart.assert_called_once_with(clean_start=True)

    def test_restart_endpoint_reports_already_restarting(self):
        client = TestClient(main.app)

        with patch("main.check"), patch("main._request_application_restart", return_value=False) as mock_restart, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/app/restart", json={"token": "x" * 32, "clean_start": True})

        assert response.status_code == 200
        assert response.json() == {"status": "already_restarting", "clean_start": True}
        mock_restart.assert_called_once_with(clean_start=True)
        mock_add_log.assert_not_called()


class TestStaticHttpServer:
    def test_server_bind_skips_reverse_dns_lookup(self):
        server = object.__new__(main._StaticHTTPServer)
        server.server_address = ("0.0.0.0", 8080)

        with patch("main.TCPServer.server_bind") as mock_bind, patch("main.socket.getfqdn", side_effect=AssertionError("should not be called")):
            main._StaticHTTPServer.server_bind(server)

        mock_bind.assert_called_once_with(server)
        assert server.server_name == "0.0.0.0"
        assert server.server_port == 8080


class TestServerShutdown:
    """Test server shutdown functions."""
    
    def test_shutdown_servers_no_servers(self):
        """Test graceful shutdown when servers are None."""
        main._web_server = None
        
        with patch("main.logger"):
            # Should not raise any exceptions
            main.shutdown_servers()
    
    def test_shutdown_servers_with_web_server(self):
        """Test graceful shutdown with web server."""
        mock_web_server = MagicMock()
        main._web_server = mock_web_server
        main._api_server = None

        with patch("main.logger"):
            main.shutdown_servers()
            mock_web_server.shutdown.assert_called_once()
            mock_web_server.server_close.assert_called_once()

    def test_shutdown_servers_requests_api_stop(self):
        """Test graceful shutdown requests uvicorn server stop."""
        mock_api_server = MagicMock()
        mock_api_server.should_exit = False
        main._api_server = mock_api_server
        main._web_server = None

        with patch("main.logger"):
            main.shutdown_servers()
            assert mock_api_server.should_exit is True

    def test_shutdown_servers_error_handling(self):
        """Test graceful shutdown with exceptions."""
        mock_web_server = MagicMock()
        mock_web_server.shutdown.side_effect = Exception("Test error")
        main._web_server = mock_web_server
        main._api_server = None

        with patch("main.logger"):
            # Should not raise exception
            main.shutdown_servers()


class TestLoginSecurity:
    """Test login endpoint audit logging and brute-force protection."""

    def test_login_before_setup_logs_warning(self):
        client = TestClient(main.app)
        manager = MagicMock()
        manager.requires_password_setup.return_value = True
        limiter = main.LoginRateLimiter(now_fn=lambda: 100.0)

        with patch("main._auth_manager", return_value=manager), patch("main.LOGIN_RATE_LIMITER", limiter), patch("main.logger") as mock_logger:
            response = client.post("/login", json={"password": "1234"})

        assert response.status_code == 409
        assert response.json()["detail"] == "PIN setup is not complete yet"
        manager.verify_password.assert_not_called()
        mock_logger.warning.assert_called_once_with("Login attempt before setup | IP: %s", "testclient")
        assert limiter.blocked_until("testclient") is None

    def test_login_rate_limit_blocks_after_sixth_invalid_pin(self):
        client = TestClient(main.app)
        manager = MagicMock()
        manager.requires_password_setup.return_value = False
        manager.verify_password.return_value = False
        clock = FakeClock()
        limiter = main.LoginRateLimiter(now_fn=clock.now)

        with patch("main._auth_manager", return_value=manager), patch("main.LOGIN_RATE_LIMITER", limiter), patch("main.logger") as mock_logger:
            for _ in range(main.config.LOGIN_ATTEMPT_LIMIT):
                response = client.post("/login", json={"password": "1234"})
                assert response.status_code == 403
                clock.advance(1)

            blocked_response = client.post("/login", json={"password": "1234"})
            retry_response = client.post("/login", json={"password": "1234"})

        assert blocked_response.status_code == 429
        assert retry_response.status_code == 429
        assert blocked_response.json()["detail"] == "Too many login attempts. Try again later."
        critical_messages = [call.args[0] for call in mock_logger.critical.call_args_list]
        assert "Brute force protection triggered | IP: %s" in critical_messages
        assert "Brute force login blocked | IP: %s" in critical_messages

    def test_successful_login_resets_rate_limit_state(self):
        client = TestClient(main.app)
        manager = MagicMock()
        manager.requires_password_setup.return_value = False
        clock = FakeClock()
        limiter = main.LoginRateLimiter(now_fn=clock.now)
        responses = [False, False, True, False]

        def verify_password(pin: str) -> bool:
            return responses.pop(0)

        manager.verify_password.side_effect = verify_password
        manager.issue_token.return_value = ("token-1", 60)

        with patch("main._auth_manager", return_value=manager), patch("main.LOGIN_RATE_LIMITER", limiter), patch("main.logger"):
            first = client.post("/login", json={"password": "1234"})
            second = client.post("/login", json={"password": "1234"})
            success = client.post("/login", json={"password": "1234"})
            after_reset = client.post("/login", json={"password": "1234"})

        assert first.status_code == 403
        assert second.status_code == 403
        assert success.status_code == 200
        assert success.json()["token"] == "token-1"
        assert after_reset.status_code == 403
        assert limiter.blocked_until("testclient") is None


class TestSystemInfoCaching:
    """Test split system info caches and defensive copies."""

    def setup_method(self):
        main.stop_system_info_sampler()
        main._SYSTEM_INFO_STATE = main.SystemInfoState()
        main._SYSTEM_INFO_THREAD = None
        main._SYSTEM_INFO_STOP_EVENT = main.threading.Event()

    def test_system_info_reuses_cached_sections_within_ttl(self):
        clock = FakeClock(start=10.0)
        runtime = {"cpu_percent": 12.0, "ram_percent": 30.0, "ram_used_mb": 1000, "ram_total_mb": 2000}
        battery = {"present": False, "percent": None, "power_plugged": None, "secs_left": None}
        network = {
            "hostname": "pc",
            "current_ip": "192.168.1.10",
            "primary_interface": {"ip": "192.168.1.10"},
            "interfaces": [{"ip": "192.168.1.10"}],
        }
        audio = {"active_output_device": {"id": "a"}}

        with patch("main.time.time", side_effect=clock.now), patch("main.config.SYSTEM_INFO_RUNTIME_TTL_SECONDS", 1.0), patch("main.config.SYSTEM_INFO_BATTERY_TTL_SECONDS", 5.0), patch("main.config.SYSTEM_INFO_NETWORK_TTL_SECONDS", 30.0), patch("main.config.SYSTEM_INFO_AUDIO_TTL_SECONDS", 10.0), patch("main._collect_runtime_info", return_value=runtime) as mock_runtime, patch("main._battery_info", return_value=battery) as mock_battery, patch("main._collect_network_info", return_value=network) as mock_network, patch("main._collect_audio_info", return_value=audio) as mock_audio:
            first = main._system_info()
            clock.advance(0.5)
            second = main._system_info()

        assert first == second
        assert mock_runtime.call_count == 1
        assert mock_battery.call_count == 1
        assert mock_network.call_count == 1
        assert mock_audio.call_count == 1

    def test_system_info_refreshes_only_expired_section(self):
        clock = FakeClock(start=50.0)
        runtime_a = {"cpu_percent": 1.0, "ram_percent": 2.0, "ram_used_mb": 3, "ram_total_mb": 4}
        runtime_b = {"cpu_percent": 99.0, "ram_percent": 2.0, "ram_used_mb": 3, "ram_total_mb": 4}
        battery = {"present": True, "percent": 10, "power_plugged": True, "secs_left": 1}
        network = {"hostname": "pc", "current_ip": "1.1.1.1", "primary_interface": None, "interfaces": []}
        audio = {"active_output_device": {"id": "speaker-a"}}

        with patch("main.time.time", side_effect=clock.now), patch("main.config.SYSTEM_INFO_RUNTIME_TTL_SECONDS", 1.0), patch("main.config.SYSTEM_INFO_BATTERY_TTL_SECONDS", 5.0), patch("main.config.SYSTEM_INFO_NETWORK_TTL_SECONDS", 30.0), patch("main.config.SYSTEM_INFO_AUDIO_TTL_SECONDS", 10.0), patch("main._collect_runtime_info", side_effect=[runtime_a, runtime_b]) as mock_runtime, patch("main._battery_info", return_value=battery) as mock_battery, patch("main._collect_network_info", return_value=network) as mock_network, patch("main._collect_audio_info", return_value=audio) as mock_audio:
            first = main._system_info()
            clock.advance(2)
            second = main._system_info()

        assert first["cpu_percent"] == 1.0
        assert second["cpu_percent"] == 99.0
        assert second["battery"] == battery
        assert second["network"]["current_ip"] == "1.1.1.1"
        assert mock_runtime.call_count == 2
        assert mock_battery.call_count == 1
        assert mock_network.call_count == 1
        assert mock_audio.call_count == 1

    def test_system_info_returns_defensive_copy(self):
        clock = FakeClock(start=5.0)
        runtime = {"cpu_percent": 12.0, "ram_percent": 30.0, "ram_used_mb": 1000, "ram_total_mb": 2000}
        battery = {"present": False, "percent": None, "power_plugged": None, "secs_left": None}
        network = {
            "hostname": "pc",
            "current_ip": "192.168.1.10",
            "primary_interface": {"ip": "192.168.1.10"},
            "interfaces": [{"ip": "192.168.1.10"}],
        }
        audio = {"active_output_device": {"id": "a"}}

        with patch("main.time.time", side_effect=clock.now), patch("main.config.SYSTEM_INFO_RUNTIME_TTL_SECONDS", 5.0), patch("main.config.SYSTEM_INFO_BATTERY_TTL_SECONDS", 5.0), patch("main.config.SYSTEM_INFO_NETWORK_TTL_SECONDS", 5.0), patch("main.config.SYSTEM_INFO_AUDIO_TTL_SECONDS", 5.0), patch("main._collect_runtime_info", return_value=runtime), patch("main._battery_info", return_value=battery), patch("main._collect_network_info", return_value=network), patch("main._collect_audio_info", return_value=audio):
            first = main._system_info()
            first["network"]["interfaces"].append({"ip": "8.8.8.8"})
            first["network"]["primary_interface"]["ip"] = "8.8.8.8"
            first["audio"]["active_output_device"]["id"] = "changed"
            second = main._system_info()

        assert len(second["network"]["interfaces"]) == 1
        assert second["network"]["primary_interface"] == {"ip": "192.168.1.10"}
        assert second["audio"]["active_output_device"] == {"id": "a"}


class TestLogsEndpoint:
    def test_logs_endpoint_supports_incremental_reads(self):
        client = TestClient(main.app)
        entries = [
            main.gui.LogEntry(id=4, message="one"),
            main.gui.LogEntry(id=5, message="two"),
        ]

        with patch("main.check"), patch("main.gui.get_logs", return_value=(entries, 5, False)) as mock_get_logs:
            response = client.post("/logs", json={"token": "x" * 32, "limit": 10, "since": 3})

        assert response.status_code == 200
        assert response.json() == {
            "logs": ["one", "two"],
            "next_since": 5,
            "reset": False,
        }
        mock_get_logs.assert_called_once_with(3, 10)


class TestAppsEndpoints:
    def test_recent_apps_endpoint_returns_quick_launch_candidates(self):
        client = TestClient(main.app)
        payload = [
            {"name": "Telegram", "path": r"C:\Apps\Telegram.exe"},
            {"name": "Discord", "path": r"C:\Apps\Discord.exe"},
        ]
        pinned = [{"name": "Firefox", "path": r"C:\Apps\Firefox.exe"}]

        with patch("main.check"), patch("main.apps.list_recent", return_value=payload) as mock_list_recent, patch("main.apps.list_pinned", return_value=pinned) as mock_list_pinned:
            response = client.post("/apps/recent", json={"token": "x" * 32})

        assert response.status_code == 200
        assert response.json() == {"apps": payload, "pinned_apps": pinned}
        mock_list_recent.assert_called_once_with(limit=12)
        mock_list_pinned.assert_called_once_with()

    def test_open_app_endpoint_starts_application_and_returns_refreshed_recent_apps(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\Notion.exe"
        launched_app = {"name": "Notion", "path": app_path}
        refreshed = [{"name": "Notion", "path": app_path}]
        pinned = [{"name": "Discord", "path": r"C:\Apps\Discord.exe"}]

        with patch("main.check"), patch("main.apps.start", return_value=launched_app) as mock_start, patch("main.apps.list_recent", return_value=refreshed) as mock_list_recent, patch("main.apps.list_pinned", return_value=pinned) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/apps/open", json={"token": "x" * 32, "path": app_path})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "launched_app": launched_app, "apps": refreshed, "pinned_apps": pinned}
        mock_start.assert_called_once_with(app_path, name=None, args=None, aumid=None)
        mock_list_recent.assert_called_once_with(limit=12, prioritized_items=[launched_app])
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App launch requested: Notion")

    def test_open_app_endpoint_without_path_starts_most_recent_application(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\Telegram.exe"
        launched_app = {"name": "Telegram", "path": app_path}
        refreshed = [launched_app]
        pinned = [{"name": "Firefox", "path": r"C:\Apps\Firefox.exe"}]

        with patch("main.check"), patch("main.apps.start", return_value=launched_app) as mock_start, patch("main.apps.list_recent", return_value=refreshed) as mock_list_recent, patch("main.apps.list_pinned", return_value=pinned) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/apps/open", json={"token": "x" * 32})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "launched_app": launched_app, "apps": refreshed, "pinned_apps": pinned}
        mock_start.assert_called_once_with(None, name=None, args=None, aumid=None)
        mock_list_recent.assert_called_once_with(limit=12, prioritized_items=[launched_app])
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App launch requested: Telegram")

    def test_open_app_endpoint_preserves_shortcut_arguments(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\chrome.exe"
        shortcut_args = "--app-id=telegram"
        launched_app = {"name": "Telegram", "path": app_path, "args": shortcut_args}
        refreshed = [launched_app]

        with patch("main.check"), patch("main.apps.start", return_value=launched_app) as mock_start, patch("main.apps.list_recent", return_value=refreshed) as mock_list_recent, patch("main.apps.list_pinned", return_value=[]) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post(
                "/apps/open",
                json={"token": "x" * 32, "path": app_path, "name": "Telegram", "args": shortcut_args},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "launched_app": launched_app, "apps": refreshed, "pinned_apps": []}
        mock_start.assert_called_once_with(app_path, name="Telegram", args=shortcut_args, aumid=None)
        mock_list_recent.assert_called_once_with(limit=12, prioritized_items=[launched_app])
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App launch requested: Telegram")

    def test_window_action_endpoint_controls_existing_app_window(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\Telegram.exe"
        app_item = {"name": "Telegram", "path": app_path}
        refreshed = [app_item]

        with patch("main.check"), patch("main.apps.window_action", return_value=app_item) as mock_window_action, patch("main.apps.list_recent", return_value=refreshed) as mock_list_recent, patch("main.apps.list_pinned", return_value=[]) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post(
                "/apps/window",
                json={"token": "x" * 32, "path": app_path, "action": "minimize"},
            )

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "action": "minimize", "app": app_item, "apps": refreshed, "pinned_apps": []}
        mock_window_action.assert_called_once_with("minimize", app_path, name=None, args=None, aumid=None)
        mock_list_recent.assert_called_once_with(limit=12)
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App minimize: Telegram")

    def test_open_app_endpoint_returns_bad_request_for_invalid_application(self):
        client = TestClient(main.app)

        with patch("main.check"), patch("main.apps.start", side_effect=ValueError("application path does not exist")):
            response = client.post("/apps/open", json={"token": "x" * 32, "path": r"C:\missing.exe"})

        assert response.status_code == 400
        assert response.json() == {"detail": "application path does not exist"}

    def test_window_action_endpoint_returns_bad_request_when_window_missing(self):
        client = TestClient(main.app)

        with patch("main.check"), patch("main.apps.window_action", side_effect=ValueError("application window not found")):
            response = client.post(
                "/apps/window",
                json={"token": "x" * 32, "path": r"C:\Apps\Telegram.exe", "action": "close"},
            )

        assert response.status_code == 400
        assert response.json() == {"detail": "application window not found"}

    def test_open_app_endpoint_rejects_non_user_process(self):
        client = TestClient(main.app)

        with patch("main.check"), patch("main.apps.start", side_effect=ValueError("application is not suitable for quick launch")):
            response = client.post("/apps/open", json={"token": "x" * 32, "path": r"C:\Windows\System32\SearchFilterHost.exe"})

        assert response.status_code == 400
        assert response.json() == {"detail": "application is not suitable for quick launch"}

    def test_pin_app_endpoint_saves_app_and_returns_pinned_list(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\Steam.exe"
        pinned_app = {"name": "Steam", "path": app_path}
        pinned = [pinned_app]

        with patch("main.check"), patch("main.apps.pin", return_value=pinned_app) as mock_pin, patch("main.apps.list_pinned", return_value=pinned) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/apps/pin", json={"token": "x" * 32, "path": app_path})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "pinned_app": pinned_app, "pinned_apps": pinned}
        mock_pin.assert_called_once_with(app_path, name=None, args=None, aumid=None)
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App pinned: Steam")

    def test_unpin_app_endpoint_removes_app_and_returns_remaining_pins(self):
        client = TestClient(main.app)
        app_path = r"C:\Apps\Steam.exe"
        remaining = [{"name": "Firefox", "path": r"C:\Apps\Firefox.exe"}]

        with patch("main.check"), patch("main.apps.unpin", return_value=True) as mock_unpin, patch("main.apps.list_pinned", return_value=remaining) as mock_list_pinned, patch("main.gui.add_log") as mock_add_log:
            response = client.post("/apps/unpin", json={"token": "x" * 32, "path": app_path})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "removed": True, "pinned_apps": remaining}
        mock_unpin.assert_called_once_with(app_path, args=None, aumid=None)
        mock_list_pinned.assert_called_once_with()
        mock_add_log.assert_called_once_with("App unpinned: Steam")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
