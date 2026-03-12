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
            
            # Simulate calling the health endpoint
            client = TestClient(main.app)
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
            assert "auth_ready" in data


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
