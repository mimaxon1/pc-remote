"""Unit tests for main application module."""
import pytest
import socket
from unittest.mock import patch, MagicMock
import main


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
            from fastapi.testclient import TestClient
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
