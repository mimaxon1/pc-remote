"""Unit tests for authentication module."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import auth


class TestPasswordHash:
    def test_password_hash_creation(self):
        ph = auth.PasswordHash.from_password("1234")
        assert ph.algorithm == auth.PBKDF2_ALGO
        assert ph.iterations == auth.PBKDF2_ITERS
        assert len(ph.salt_b64) > 0
        assert len(ph.hash_b64) > 0

    def test_password_verification(self):
        ph = auth.PasswordHash.from_password("1234")
        assert ph.verify("1234") is True
        assert ph.verify("5678") is False

    def test_password_hash_consistency(self):
        password = "correct-password"
        ph = auth.PasswordHash.from_password(password)
        for _ in range(5):
            assert ph.verify(password) is True


class TestTokenStore:
    def test_token_issue(self):
        store = auth.TokenStore(ttl_seconds=3600)
        token, ttl = store.issue()

        assert token is not None
        assert len(token) > 0
        assert ttl == 3600
        assert store.verify(token) is True

    def test_token_expiration(self):
        store = auth.TokenStore(ttl_seconds=1)
        token, _ = store.issue()

        assert store.verify(token) is True

        import time

        time.sleep(1.1)
        assert store.verify(token) is False

    def test_pair_token_tracking(self):
        store = auth.TokenStore()
        token, _ = store.issue_pair()

        opened, completed = store.get_pair_status(token)
        assert opened is False
        assert completed is False

        store.mark_pair_opened(token)
        opened, completed = store.get_pair_status(token)
        assert opened is True
        assert completed is False

        store.mark_pair_completed(token)
        opened, completed = store.get_pair_status(token)
        assert opened is True
        assert completed is True

    def test_revoke_clears_pair_token_state(self):
        store = auth.TokenStore()
        token, _ = store.issue_pair()

        store.revoke(token)

        assert store.verify(token) is False
        assert store.get_pair_status(token) == (False, False)


class TestAuthManager:
    def setup_method(self):
        self.temp_dir = Path(".test-auth-work")
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("auth.settings_path")
    def test_auth_manager_creation_requires_qr_setup(self, mock_path):
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file

        manager = auth.AuthManager()

        assert manager is not None
        assert manager.requires_password_setup() is True
        assert manager.verify_password("1234") is False

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["password"]["is_set"] is False

    @patch("auth.settings_path")
    def test_setup_password_enables_verification(self, mock_path):
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file

        manager = auth.AuthManager()
        token, ttl = manager.setup_password("1234")

        assert manager.requires_password_setup() is False
        assert manager.verify_password("1234") is True
        assert manager.verify_token(token) is True
        assert ttl > 0

    @patch("auth.settings_path")
    def test_change_password_invalidates_old_pin(self, mock_path):
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file

        manager = auth.AuthManager()
        manager.setup_password("1234")
        manager.change_password("5678")

        assert manager.verify_password("1234") is False
        assert manager.verify_password("5678") is True

    @patch("auth.settings_path")
    def test_legacy_default_pin_is_migrated_to_setup_required(self, mock_path):
        settings_file = self.temp_dir / "settings.json"
        mock_path.return_value = settings_file

        password_hash = auth.PasswordHash.from_password("1234")
        settings_file.write_text(
            json.dumps(
                {
                    "version": 2,
                    "password": {
                        "algorithm": password_hash.algorithm,
                        "iterations": password_hash.iterations,
                        "salt": password_hash.salt_b64,
                        "hash": password_hash.hash_b64,
                        "is_default": True,
                    },
                }
            ),
            encoding="utf-8",
        )

        manager = auth.AuthManager()

        assert manager.requires_password_setup() is True
        assert manager.verify_password("1234") is False

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["version"] == auth.SETTINGS_VERSION
        assert data["password"] == {"is_set": False}


class TestPersistedSettingsCleanup:
    def test_remove_persisted_settings_deletes_existing_files(self, tmp_path: Path):
        current = tmp_path / "current" / "settings.json"
        legacy = tmp_path / "legacy" / "settings.json"
        runtime = tmp_path / "runtime" / "settings.json"

        for path in (current, legacy, runtime):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

        with patch("auth.settings_candidates", return_value=[current, legacy, runtime]):
            removed = auth.remove_persisted_settings()

        assert removed == [current, legacy, runtime]
        for path in (current, legacy, runtime):
            assert path.exists() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
