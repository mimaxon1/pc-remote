"""Authentication helpers (PIN hashing + session tokens)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import config

SETTINGS_VERSION = 3

PBKDF2_ALGO = "pbkdf2_hmac_sha256"
PBKDF2_ITERS = 200_000
SALT_BYTES = 16

logger = logging.getLogger(config.LOGGER_NAME)


class SettingsError(RuntimeError):
    """Raised when settings.json exists but cannot be used safely."""


def app_dir() -> Path:
    """Directory where persistent settings should live."""
    return config.app_dir()


def _legacy_runtime_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _legacy_runtime_settings_path() -> Path:
    return _legacy_runtime_app_dir() / config.SETTINGS_FILENAME


def _legacy_appdata_settings_paths() -> list[Path]:
    base = config.appdata_base_dir()
    if base is None:
        return []
    return [base / name / config.SETTINGS_FILENAME for name in config.LEGACY_APP_NAMES]


def _migrate_from_source(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    try:
        if source.resolve() == target.resolve():
            return False
    except Exception as exc:
        logger.warning("Failed to resolve legacy settings path %s: %s", source, exc)

    if target.exists():
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(target))
        return True
    except Exception as exc:
        logger.warning("Failed to move legacy settings %s -> %s: %s", source, target, exc)
        try:
            shutil.copy2(source, target)
            source.unlink(missing_ok=True)
            return True
        except Exception as copy_exc:
            logger.exception("Failed to migrate legacy settings %s -> %s: %s", source, target, copy_exc)
            return False


def _migrate_legacy_settings(target: Path) -> None:
    candidates = _legacy_appdata_settings_paths()
    candidates.append(_legacy_runtime_settings_path())
    for source in candidates:
        if _migrate_from_source(source, target):
            break


def settings_path() -> Path:
    path = app_dir() / config.SETTINGS_FILENAME
    _migrate_legacy_settings(path)
    return path


def settings_candidates() -> list[Path]:
    candidates = [app_dir() / config.SETTINGS_FILENAME]
    candidates.extend(_legacy_appdata_settings_paths())
    candidates.append(_legacy_runtime_settings_path())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def remove_persisted_settings() -> list[Path]:
    removed: list[Path] = []
    for path in settings_candidates():
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(path)
        except Exception as exc:
            logger.warning("Failed to remove settings file %s: %s", path, exc)
            continue

        parent = path.parent
        try:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
    return removed


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
        """Verify a candidate PIN against the stored hash."""
        if self.algorithm != PBKDF2_ALGO:
            return False
        try:
            salt = _b64d(self.salt_b64)
            expected = _b64d(self.hash_b64)
        except Exception as exc:
            logger.warning("Failed to decode stored PIN hash: %s", exc)
            return False

        candidate = _pbkdf2_sha256(password, salt, self.iterations)
        return hmac.compare_digest(candidate, expected)

    @staticmethod
    def from_password(password: str, iterations: int = PBKDF2_ITERS) -> "PasswordHash":
        """Create a stored hash for a freshly chosen PIN."""
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
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
            tmp_name = f.name
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


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


def _password_setup_payload() -> dict[str, bool]:
    return {"is_set": False}


def _password_hash_payload(ph: PasswordHash) -> dict[str, Any]:
    return {
        "is_set": True,
        "algorithm": ph.algorithm,
        "iterations": ph.iterations,
        "salt": ph.salt_b64,
        "hash": ph.hash_b64,
    }


def save_password_hash(ph: PasswordHash) -> None:
    settings = _load_settings()
    settings["version"] = SETTINGS_VERSION
    settings["password"] = _password_hash_payload(ph)
    _save_settings(settings)


def clear_password_setup_state() -> None:
    settings = _load_settings()
    settings["version"] = SETTINGS_VERSION
    settings["password"] = _password_setup_payload()
    _save_settings(settings)


def _validate_loaded_password_hash(ph: PasswordHash) -> None:
    if ph.algorithm != PBKDF2_ALGO:
        raise SettingsError("settings.json has an unsupported password algorithm")
    if int(ph.iterations) <= 0:
        raise SettingsError("settings.json has an invalid password block")
    try:
        salt = _b64d(ph.salt_b64)
        digest = _b64d(ph.hash_b64)
    except Exception as exc:
        raise SettingsError("settings.json has an invalid password block") from exc
    if not salt or not digest:
        raise SettingsError("settings.json has an invalid password block")


def _parse_password_hash(raw: dict[str, Any]) -> tuple[Optional[PasswordHash], bool]:
    pw = raw.get("password")
    if pw is None:
        return None, True
    if not isinstance(pw, dict):
        raise SettingsError("settings.json has an invalid password block")

    if bool(pw.get("is_default", False)):
        logger.warning("Legacy default PIN detected; forcing QR setup on next launch")
        return None, True

    is_set = bool(pw.get("is_set", True))
    if not is_set:
        return None, True

    try:
        ph = PasswordHash(
            algorithm=str(pw.get("algorithm", "")),
            iterations=int(pw.get("iterations", 0)),
            salt_b64=str(pw.get("salt", "")),
            hash_b64=str(pw.get("hash", "")),
        )
    except Exception as exc:
        raise SettingsError("settings.json has an invalid password block") from exc
    _validate_loaded_password_hash(ph)
    return ph, False


def load_or_init_password_hash() -> tuple[Optional[PasswordHash], bool]:
    """Load the PIN hash from settings.json or initialize QR-only setup state."""
    path = settings_path()
    if path.exists():
        raw = _load_settings()
        ph, requires_setup = _parse_password_hash(raw)
        password_block = raw.get("password")
        needs_rewrite = int(raw.get("version", 0)) < SETTINGS_VERSION
        if requires_setup:
            if needs_rewrite or not isinstance(password_block, dict) or password_block.get("is_set", True):
                clear_password_setup_state()
        elif ph is not None and needs_rewrite:
            save_password_hash(ph)
        return ph, requires_setup

    clear_password_setup_state()
    return None, True


class TokenStore:
    """In-memory token store (tokens are lost on app restart)."""

    def __init__(self, ttl_seconds: int = config.TOKEN_TTL_SECONDS) -> None:
        self._ttl = int(ttl_seconds)
        self._lock = threading.Lock()
        self._tokens: dict[str, dict[str, float]] = {}
        self._pair_tokens: dict[str, dict[str, float | bool]] = {}

    def _issue_locked(self, track_pair: bool) -> tuple[str, int]:
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

    def _discard_locked(self, token: str) -> None:
        self._tokens.pop(token, None)
        self._pair_tokens.pop(token, None)

    def issue(self) -> tuple[str, int]:
        with self._lock:
            return self._issue_locked(track_pair=False)

    def issue_pair(self) -> tuple[str, int]:
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
                self._discard_locked(token)
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
                self._discard_locked(token)
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
                self._discard_locked(token)
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
                self._discard_locked(token)
                return False, False
            return bool(item.get("opened")), bool(item.get("completed"))

    def revoke(self, token: str) -> None:
        with self._lock:
            self._discard_locked(token)

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()
            self._pair_tokens.clear()


class AuthManager:
    """High-level auth wrapper used by the API."""

    def __init__(self) -> None:
        self._password_hash, self._requires_password_setup = load_or_init_password_hash()
        self.tokens = TokenStore()
        self._lock = threading.Lock()

    def verify_password(self, password: str) -> bool:
        """Verify a PIN entered by the user."""
        if self._password_hash is None:
            return False
        return self._password_hash.verify(password)

    def requires_password_setup(self) -> bool:
        return self._requires_password_setup

    def issue_token(self) -> tuple[str, int]:
        return self.tokens.issue()

    def issue_pair_token(self) -> tuple[str, int]:
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
        """Replace the current PIN and revoke existing sessions."""
        with self._lock:
            self._password_hash = PasswordHash.from_password(new_password)
            self._requires_password_setup = False
            save_password_hash(self._password_hash)
            self.tokens.clear()

    def setup_password(self, new_password: str) -> tuple[str, int]:
        """Store the first PIN after QR setup and issue a fresh session."""
        with self._lock:
            self._password_hash = PasswordHash.from_password(new_password)
            self._requires_password_setup = False
            save_password_hash(self._password_hash)
            self.tokens.clear()
            return self.tokens.issue()
