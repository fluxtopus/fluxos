"""Security-focused tests for session-bound authentication."""

import pytest

from src.database.models import Session as SessionModel, User
from src.security.jwt import decode_token
from src.services.auth_service import AuthService, hash_token


@pytest.mark.unit
def test_login_creates_session_bound_tokens(db):
    """Login should issue tokens tied to a persisted session id."""
    AuthService.register_user(db, "session-user@example.com", "test_password_123")
    user = db.query(User).filter(User.email == "session-user@example.com").first()
    user.status = "active"
    db.commit()

    result = AuthService.login_user(db, "session-user@example.com", "test_password_123")
    payload = decode_token(result["access_token"])

    assert payload is not None
    assert payload.get("sid")

    db_session = db.query(SessionModel).filter(
        SessionModel.user_id == user.id,
        SessionModel.token_hash == hash_token(payload["sid"]),
    ).first()
    assert db_session is not None


@pytest.mark.unit
def test_refresh_requires_active_session(db):
    """Refresh token must fail after session invalidation."""
    AuthService.register_user(db, "refresh-user@example.com", "test_password_123")
    user = db.query(User).filter(User.email == "refresh-user@example.com").first()
    user.status = "active"
    db.commit()

    tokens = AuthService.login_user(db, "refresh-user@example.com", "test_password_123")
    AuthService.invalidate_all_user_sessions(db, user.id)

    with pytest.raises(ValueError, match="Invalid refresh token"):
        AuthService.refresh_access_token(db, tokens["refresh_token"])


@pytest.mark.unit
def test_get_current_user_rejects_revoked_session(db):
    """Access token should stop working once its session is revoked."""
    AuthService.register_user(db, "current-user@example.com", "test_password_123")
    user = db.query(User).filter(User.email == "current-user@example.com").first()
    user.status = "active"
    db.commit()

    tokens = AuthService.login_user(db, "current-user@example.com", "test_password_123")
    assert AuthService.get_current_user(db, tokens["access_token"]) is not None

    AuthService.invalidate_all_user_sessions(db, user.id)
    assert AuthService.get_current_user(db, tokens["access_token"]) is None


@pytest.mark.unit
def test_logout_by_jwt_invalidates_session(db):
    """Logout should invalidate the bound session."""
    AuthService.register_user(db, "logout-user@example.com", "test_password_123")
    user = db.query(User).filter(User.email == "logout-user@example.com").first()
    user.status = "active"
    db.commit()

    tokens = AuthService.login_user(db, "logout-user@example.com", "test_password_123")
    assert AuthService.logout_by_jwt(db, tokens["access_token"]) is True
    assert AuthService.get_current_user(db, tokens["access_token"]) is None

