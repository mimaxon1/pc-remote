"""Authentication helpers (password hashing + session tokens).

Goals:
- Allow changing password without rebuilding the app (settings.json next to exe)
- Avoid sending the password with every request (login -> token -> token auth)

Notes:
- This is still plain HTTP by default, so tokens can be sniffed on an unsafe LAN.
  The big win is that the password is sent only once per session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple


SETTINGS_FILENAME = "settings.json"
SETTINGS_VERSION = 2

PBKDF2_ALGO = "pbkdf2_hmac_sha256"
PBKDF2_ITERS = 200_000
SALT_BYTES = 16

TOKEN_TTL_SECONDS = 60 * 60  # 1 hour


class SettingsError(RuntimeError):
    """Raised when settings.json exists but cannot be used safely."""


def app_dir() -> Path:
    """Directory where persistent settings should live."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def settings_path() -> Path:
    return app_dir() / SETTINGS_FILENAME


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _pbkdf2_sha256(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


@dataclass(frozen=True)
class PasswordHash:
    algorithm: str
    iterations: int
    salt_b64: str
    hash_b64: str

    def verify(self, password: str) -> bool:
        if self.algorithm != PBKDF2_ALGO:
            return False
        try:
            salt = _b64d(self.salt_b64)
            expected = _b64d(self.hash_b64)
        except Exception:
            return False

        candidate = _pbkdf2_sha256(password, salt, self.iterations)
        return hmac.compare_digest(candidate, expected)

    @staticmethod
    def from_password(password: str, iterations: int = PBKDF2_ITERS) -> "PasswordHash":
        salt = os.urandom(SALT_BYTES)
        digest = _pbkdf2_sha256(password, salt, iterations)
        return PasswordHash(
            algorithm=PBKDF2_ALGO,
            iterations=int(iterations),
            salt_b64=_b64e(salt),
            hash_b64=_b64e(digest),
        )


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp_dir = path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
        tmp_name = f.name
    os.replace(tmp_name, path)


def _load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SettingsError(f"Could not read {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"{path.name} must contain a JSON object")
    return raw


def _save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    _atomic_write_json(path, data)


def _parse_password_hash(raw: dict[str, Any], default_password: str) -> tuple[PasswordHash, bool, bool]:
    try:
        pw = raw["password"]
        if not isinstance(pw, dict):
            raise TypeError("password must be an object")
        ph = PasswordHash(
            algorithm=str(pw.get("algorithm", "")),
            iterations=int(pw.get("iterations", 0)),
            salt_b64=str(pw.get("salt", "")),
            hash_b64=str(pw.get("hash", "")),
        )
    except Exception as exc:
        raise SettingsError("settings.json has an invalid password block") from exc

    has_is_default = "is_default" in pw
    is_default = bool(pw.get("is_default", False)) if has_is_default else ph.verify(default_password)
    return ph, is_default, has_is_default


def load_or_init_password_hash(default_password: str) -> tuple[PasswordHash, bool]:
    """Load password hash from settings.json, or create it on first run."""
    path = settings_path()
    if path.exists():
        raw = _load_settings()
        ph, is_default, has_is_default = _parse_password_hash(raw, default_password)
        if int(raw.get("version", 0)) < SETTINGS_VERSION or not has_is_default:
            save_password_hash(ph, is_default=is_default)
        return ph, is_default

    ph = PasswordHash.from_password(default_password)
    save_password_hash(ph, is_default=True)
    return ph, True


def save_password_hash(ph: PasswordHash, is_default: bool) -> None:
    settings = _load_settings()
    settings["version"] = SETTINGS_VERSION
    settings["password"] = {
        "algorithm": ph.algorithm,
        "iterations": ph.iterations,
        "salt": ph.salt_b64,
        "hash": ph.hash_b64,
        "is_default": bool(is_default),
    }
    _save_settings(settings)


class TokenStore:
    """In-memory token store (tokens are lost on app restart)."""

    def __init__(self, ttl_seconds: int = TOKEN_TTL_SECONDS) -> None:
        self._ttl = int(ttl_seconds)
        self._lock = threading.Lock()
        self._tokens: dict[str, dict[str, float]] = {}
        self._pair_tokens: dict[str, dict[str, float | bool]] = {}

    def _issue_locked(self, track_pair: bool) -> Tuple[str, int]:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self._ttl
        self._tokens[token] = {"expires_at": expires_at}
        if track_pair:
            self._pair_tokens[token] = {
                "expires_at": expires_at,
                "opened": False,
                "completed": False,
            }
        return token, self._ttl

    def issue(self) -> Tuple[str, int]:
        with self._lock:
            return self._issue_locked(track_pair=False)

    def issue_pair(self) -> Tuple[str, int]:
        with self._lock:
            return self._issue_locked(track_pair=True)

    def verify(self, token: str) -> bool:
        if not token:
            return False

        now = time.time()
        with self._lock:
            item = self._tokens.get(token)
            if item is None:
                return False
            expires_at = float(item["expires_at"])
            if expires_at <= now:
                self._tokens.pop(token, None)
                self._pair_tokens.pop(token, None)
                return False
            return True

    def mark_pair_opened(self, token: str) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            item = self._pair_tokens.get(token)
            if item is None:
                return False
            if float(item["expires_at"]) <= now:
                self._pair_tokens.pop(token, None)
                return False
            item["opened"] = True
            return True

    def mark_pair_completed(self, token: str) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            item = self._pair_tokens.get(token)
            if item is None:
                return False
            if float(item["expires_at"]) <= now:
                self._pair_tokens.pop(token, None)
                return False
            item["completed"] = True
            return True

    def get_pair_status(self, token: str) -> tuple[bool, bool]:
        if not token:
            return False, False
        now = time.time()
        with self._lock:
            item = self._pair_tokens.get(token)
            if item is None:
                return False, False
            if float(item["expires_at"]) <= now:
                self._pair_tokens.pop(token, None)
                return False, False
            return bool(item.get("opened")), bool(item.get("completed"))

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()


class AuthManager:
    """High-level auth wrapper used by the API."""

    def __init__(self, default_password: str) -> None:
        self._password_hash, self._password_is_default = load_or_init_password_hash(default_password)
        self.tokens = TokenStore()
        self._lock = threading.Lock()

    def verify_password(self, password: str) -> bool:
        return self._password_hash.verify(password)

    def requires_password_setup(self) -> bool:
        return self._password_is_default

    def issue_token(self) -> Tuple[str, int]:
        return self.tokens.issue()

    def issue_pair_token(self) -> Tuple[str, int]:
        return self.tokens.issue_pair()

    def verify_token(self, token: str) -> bool:
        return self.tokens.verify(token)

    def mark_pair_touched(self, token: str) -> bool:
        return self.tokens.mark_pair_opened(token)

    def is_pair_touched(self, token: str) -> bool:
        opened, _ = self.tokens.get_pair_status(token)
        return opened

    def mark_pair_completed(self, token: str) -> bool:
        return self.tokens.mark_pair_completed(token)

    def get_pair_status(self, token: str) -> tuple[bool, bool]:
        return self.tokens.get_pair_status(token)

    def change_password(self, new_password: str) -> None:
        with self._lock:
            self._password_hash = PasswordHash.from_password(new_password)
            self._password_is_default = False
            save_password_hash(self._password_hash, is_default=False)
            self.tokens.clear()

    def setup_password(self, new_password: str) -> Tuple[str, int]:
        with self._lock:
            self._password_hash = PasswordHash.from_password(new_password)
            self._password_is_default = False
            save_password_hash(self._password_hash, is_default=False)
            self.tokens.clear()
            return self.tokens.issue()
