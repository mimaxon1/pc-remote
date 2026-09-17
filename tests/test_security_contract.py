"""Defensive unit contracts; no real network or system actions."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import main


def test_legacy_pin_guard_checks_budget_before_hash(monkeypatch):
    assert hasattr(main, '_verify_legacy_pin'), 'legacy PIN budget guard missing'
    manager = MagicMock()
    limiter = MagicMock()
    limiter.blocked_until.return_value = 100
    monkeypatch.setattr(main, 'LOGIN_RATE_LIMITER', limiter)
    with pytest.raises(HTTPException) as exc:
        main._verify_legacy_pin(manager, 'test-only')
    assert exc.value.status_code == 429
    manager.verify_password.assert_not_called()


def test_server_disables_forwarded_identity_trust(monkeypatch):
    server = MagicMock()
    conf = MagicMock()
    monkeypatch.setattr(main.uvicorn, 'Config', conf)
    monkeypatch.setattr(main.uvicorn, 'Server', lambda cfg: server)
    main.run_api()
    assert conf.call_args.kwargs.get('proxy_headers') is False


def test_legacy_budget_is_charged_on_failure_and_reset_on_success(monkeypatch):
    manager = MagicMock()
    limiter = MagicMock()
    limiter.blocked_until.return_value = None
    limiter.record_failure.return_value = None
    monkeypatch.setattr(main, 'LOGIN_RATE_LIMITER', limiter)
    manager.verify_password.return_value = False
    assert main._verify_legacy_pin(manager, 'test-only') is False
    limiter.record_failure.assert_called_once_with('legacy-pin-actions')
    manager.verify_password.return_value = True
    assert main._verify_legacy_pin(manager, 'test-only') is True
    limiter.reset.assert_called_once_with('legacy-pin-actions')


def test_browser_origin_policy_is_explicit():
    assert hasattr(main, '_browser_origin_allowed'), 'explicit origin policy missing'
    assert main._browser_origin_allowed(None)
    assert main._browser_origin_allowed(main.allowed_origins[0])
    assert not main._browser_origin_allowed('https://untrusted.invalid')
    assert not main._browser_origin_allowed('null')


def test_token_authorization_does_not_use_legacy_pin_budget(monkeypatch):
    manager = MagicMock()
    manager.requires_password_setup.return_value = False
    manager.verify_token.return_value = True
    guard = MagicMock()
    monkeypatch.setattr(main, '_auth_manager', lambda: manager)
    monkeypatch.setattr(main, '_verify_legacy_pin', guard)
    main.check('test-token', None)
    guard.assert_not_called()
