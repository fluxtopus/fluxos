"""Unit tests for auth service"""

import pytest
from src.services.auth_service import AuthService
from src.database.models import User, Organization, Session as SessionModel


@pytest.mark.unit
def test_register_user(db):
    """Test user registration"""
    result = AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123",
        "Test Organization"
    )
    
    assert "user_id" in result
    assert result["email"] == "test@example.com"
    assert "organization_id" in result
    
    # Verify user was created
    user = db.query(User).filter(User.email == "test@example.com").first()
    assert user is not None
    assert user.email == "test@example.com"


@pytest.mark.unit
def test_register_user_duplicate_email(db):
    """Test registration with duplicate email fails"""
    AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123"
    )
    
    # Avoids disclosing account existence (prevents enumeration).
    with pytest.raises(ValueError, match="Registration could not be completed"):
        AuthService.register_user(
            db,
            "test@example.com",
            "test_password_123"
        )


@pytest.mark.unit
def test_login_user_success(db):
    """Test successful login"""
    # Register user first
    result = AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123"
    )

    # Newly registered users start in "pending" (email verification required).
    user = db.query(User).filter(User.id == result["user_id"]).first()
    user.status = "active"
    db.commit()
    
    result = AuthService.login_user(
        db,
        "test@example.com",
        "test_password_123"
    )
    
    assert "access_token" in result
    assert "refresh_token" in result
    assert result["token_type"] == "bearer"


@pytest.mark.unit
def test_login_user_invalid_password(db):
    """Test login with invalid password"""
    AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123"
    )

    with pytest.raises(ValueError, match="Invalid"):
        AuthService.login_user(
            db,
            "test@example.com",
            "wrong_password"
        )


@pytest.mark.unit
def test_invalidate_all_user_sessions(db):
    """Test invalidating all sessions for a user on password change"""
    # Register and activate user
    result = AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123"
    )
    user_id = result["user_id"]

    # Activate user so they can login
    user = db.query(User).filter(User.id == user_id).first()
    user.status = "active"
    db.commit()

    # Create multiple sessions by logging in multiple times
    AuthService.login_user(db, "test@example.com", "test_password_123")
    AuthService.login_user(db, "test@example.com", "test_password_123")
    AuthService.login_user(db, "test@example.com", "test_password_123")

    # Verify sessions were created
    session_count = db.query(SessionModel).filter(SessionModel.user_id == user_id).count()
    assert session_count == 3

    # Invalidate all sessions
    invalidated = AuthService.invalidate_all_user_sessions(db, user_id)

    # Verify all sessions were invalidated
    assert invalidated == 3
    remaining = db.query(SessionModel).filter(SessionModel.user_id == user_id).count()
    assert remaining == 0


@pytest.mark.unit
def test_invalidate_all_user_sessions_no_sessions(db):
    """Test invalidating sessions when user has none"""
    # Register user but don't login
    result = AuthService.register_user(
        db,
        "test@example.com",
        "test_password_123"
    )
    user_id = result["user_id"]

    # Invalidate should return 0 and not error
    invalidated = AuthService.invalidate_all_user_sessions(db, user_id)
    assert invalidated == 0
