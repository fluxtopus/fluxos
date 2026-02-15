"""Authentication service"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
import hashlib
import re
import secrets
from src.database.models import User, Organization, UserOrganization, Session as SessionModel
from src.security.password import hash_password, verify_password
from src.security.jwt import create_access_token, create_refresh_token, decode_token
from src.config import settings


def generate_session_token() -> str:
    """Generate a session token"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage"""
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    """Authentication service"""

    @staticmethod
    def _get_active_session(db: Session, user_id: str, session_id: str) -> Optional[SessionModel]:
        """Get active, non-expired session by user + session identifier."""
        return db.query(SessionModel).filter(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.token_hash == hash_token(session_id),
                SessionModel.expires_at > datetime.utcnow(),
            )
        ).first()
    
    @staticmethod
    def register_user(
        db: Session,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register a new user and create an organization"""
        # Validate password
        from src.security.password import validate_password
        validate_password(password)

        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            # Avoid disclosing account existence.
            raise ValueError("Registration could not be completed")

        # Generate organization name from first name if not provided
        if not organization_name:
            if first_name:
                organization_name = f"{first_name}'s Organization"
            else:
                domain = email.split("@")[1].split(".")[0]
                organization_name = f"{domain.capitalize()} Organization"

        # Generate unique slug from name
        base_slug = re.sub(r'[^a-z0-9]+', '-', organization_name.lower()).strip('-')
        slug = base_slug
        counter = 1
        # Ensure slug is unique
        while db.query(Organization).filter(Organization.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Create organization (always)
        organization = Organization(
            name=organization_name,
            slug=slug
        )
        db.add(organization)
        db.flush()

        # Create user with pending status (requires email verification)
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            organization_id=organization.id,
            status="pending"
        )
        db.add(user)
        db.flush()

        # Create user-organization relationship with owner role
        user_org = UserOrganization(
            user_id=user.id,
            organization_id=organization.id,
            role="owner",
            is_primary=True
        )
        db.add(user_org)
        db.commit()
        db.refresh(user)

        return {
            "user_id": user.id,
            "email": user.email,
            "organization_id": user.organization_id,
            "status": user.status
        }
    
    @staticmethod
    def login_user(
        db: Session,
        email: str,
        password: str,
        two_fa_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate a user and return tokens"""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError("Invalid email or password")
        
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        if user.status == "pending":
            raise ValueError("Email not verified. Please check your email for the verification code.")

        if user.status != "active":
            raise ValueError("User account is not active")
        
        # Check 2FA if enabled
        if user.two_fa_enabled:
            if not two_fa_code:
                raise ValueError("2FA code required")
            from src.security.two_fa import verify_2fa_code
            if not verify_2fa_code(user.two_fa_secret, two_fa_code):
                raise ValueError("Invalid 2FA code")
        
        # Create tokens
        session_token = generate_session_token()
        token_data = {
            "sub": user.id,
            "email": user.email,
            "organization_id": user.organization_id,
            "sid": session_token,
        }
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        # Create session
        session = SessionModel(
            user_id=user.id,
            token_hash=hash_token(session_token),
            expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
        db.add(session)
        db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    @staticmethod
    def logout_user(db: Session, token_hash: str) -> bool:
        """Logout a user by invalidating their session"""
        session = db.query(SessionModel).filter(
            SessionModel.token_hash == token_hash
        ).first()
        if session:
            db.delete(session)
            db.commit()
            return True
        return False

    @staticmethod
    def logout_by_jwt(db: Session, token: str) -> bool:
        """Logout using JWT by extracting and invalidating session id."""
        payload = decode_token(token)
        if not payload:
            return False

        session_id = payload.get("sid")
        if not session_id:
            return False

        return AuthService.logout_user(db, hash_token(session_id))

    @staticmethod
    def invalidate_all_user_sessions(db: Session, user_id: str) -> int:
        """Invalidate all sessions for a user (e.g., on password change)"""
        result = db.query(SessionModel).filter(
            SessionModel.user_id == user_id
        ).delete()
        db.commit()
        return result
    
    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Dict[str, Any]:
        """Refresh an access token using a refresh token"""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise ValueError("Invalid refresh token")
        
        user_id = payload.get("sub")
        session_id = payload.get("sid")
        if not user_id or not session_id:
            raise ValueError("Invalid refresh token")

        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != "active":
            raise ValueError("Invalid refresh token")

        session = AuthService._get_active_session(db, user.id, session_id)
        if not session:
            raise ValueError("Invalid refresh token")
        
        # Create new access token
        token_data = {
            "sub": user.id,
            "email": user.email,
            "organization_id": user.organization_id,
            "sid": session_id,
        }
        access_token = create_access_token(token_data)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    @staticmethod
    def get_current_user(db: Session, token: str) -> Optional[User]:
        """Get current user from JWT token"""
        payload = decode_token(token)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        session_id = payload.get("sid")
        if not user_id or not session_id:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != "active":
            return None

        session = AuthService._get_active_session(db, user.id, session_id)
        if not session:
            return None
        
        return user

