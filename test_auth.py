"""Unit tests for authentication module."""
import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import auth


class TestPasswordHash:
    """Test PasswordHash class."""
    
    def test_password_hash_creation(self):
        """Test creating a password hash."""
        ph = auth.PasswordHash.from_password("1234")
        assert ph.algorithm == auth.PBKDF2_ALGO
        assert ph.iterations == auth.PBKDF2_ITERS
        assert len(ph.salt_b64) > 0
        assert len(ph.hash_b64) > 0
    
    def test_password_verification(self):
        """Test password verification."""
        ph = auth.PasswordHash.from_password("1234")
        assert ph.verify("1234") is True
        assert ph.verify("5678") is False
    
    def test_password_hash_consistency(self):
        """Test that same password always verifies same hash."""
        password = "correct-password"
        ph = auth.PasswordHash.from_password(password)
        
        # Should always verify correctly
        for _ in range(5):
            assert ph.verify(password) is True


class TestTokenStore:
    """Test TokenStore class."""
    
    def test_token_issue(self):
        """Test issuing a token."""
        store = auth.TokenStore(ttl_seconds=3600)
        token, ttl = store.issue()
        
        assert token is not None
        assert len(token) > 0
        assert ttl == 3600
        assert store.verify(token) is True
    
    def test_token_expiration(self):
        """Test token expiration."""
        store = auth.TokenStore(ttl_seconds=1)
        token, _ = store.issue()
        
        assert store.verify(token) is True
        
        # After expiration, token should not verify
        import time
        time.sleep(1.1)
        assert store.verify(token) is False
    
    def test_pair_token_tracking(self):
        """Test pair token status tracking."""
        store = auth.TokenStore()
        token, _ = store.issue_pair()
        
        opened, completed = store.get_pair_status(token)
        assert opened is False
        assert completed is False
        
        # Mark as opened
        store.mark_pair_opened(token)
        opened, completed = store.get_pair_status(token)
        assert opened is True
        assert completed is False
        
        # Mark as completed
        store.mark_pair_completed(token)
        opened, completed = store.get_pair_status(token)
        assert opened is True
        assert completed is True


class TestAuthManager:
    """Test AuthManager class."""
    
    def setup_method(self):
        """Setup test with temporary settings file."""
        self.temp_dir = Path(".test-auth-work")
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.original_home = os.environ.get("USERPROFILE", os.environ.get("HOME"))
    
    def teardown_method(self):
        """Cleanup temporary files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch("auth.settings_path")
    def test_auth_manager_creation(self, mock_path):
        """Test AuthManager initialization."""
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file
        
        manager = auth.AuthManager(default_password="1234")
        
        assert manager is not None
        assert manager.requires_password_setup() is True
    
    @patch("auth.settings_path")
    def test_password_verification(self, mock_path):
        """Test password verification through AuthManager."""
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file
        
        manager = auth.AuthManager(default_password="1234")
        
        # Default password should verify
        assert manager.verify_password("1234") is True
        assert manager.verify_password("wrong") is False
    
    @patch("auth.settings_path")
    def test_token_issuance(self, mock_path):
        """Test token issuance and verification."""
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file
        
        manager = auth.AuthManager(default_password="1234")
        token, ttl = manager.issue_token()
        
        assert manager.verify_token(token) is True
        assert ttl > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
