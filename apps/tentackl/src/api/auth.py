# REVIEW:
# - Duplicates auth concerns with auth_middleware.py (JWT, scopes); unclear which is canonical.
# - SECRET_KEY is read at import time; tests/env overrides later won't affect this module.
# - User.metadata and User.scopes use mutable defaults; should use default_factory to avoid shared state.
"""Authentication and authorization for the API."""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import logging
from src.core.config import settings

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()

# Configuration — no insecure fallback (SEC-003)
SECRET_KEY = os.getenv("TENTACKL_SECRET_KEY") or settings.SECRET_KEY or ""
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class TokenData(BaseModel):
    """Token payload data."""
    sub: str  # Subject (user ID)
    exp: datetime
    iat: datetime
    scopes: list[str] = []


class User(BaseModel):
    """User model."""
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool = True
    scopes: list[str] = []
    metadata: Dict[str, Any] = {}  # Extra data from JWT (organization_id, etc.)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> User:
    """Get the current authenticated user from the token."""
    token = credentials.credentials
    
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract user info from JWT payload
        # InkPass tokens include organization_id which we need for file storage
        metadata = {}
        if payload.get("organization_id"):
            metadata["organization_id"] = payload.get("organization_id")

        user = User(
            id=user_id,
            username=payload.get("username", user_id),
            email=payload.get("email"),
            scopes=payload.get("scopes", []),
            metadata=metadata
        )

        return user
        
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_scopes(*required_scopes: str):
    """Dependency to require specific scopes."""
    async def scope_checker(current_user: User = Security(get_current_user)):
        for scope in required_scopes:
            if scope not in current_user.scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Not enough permissions. Required scope: {scope}"
                )
        return current_user
    
    return scope_checker


# Scope definitions
class Scopes:
    """API scope definitions.

    DEPRECATED: This class is kept for backwards compatibility only.
    New code should use auth_middleware.require_permission() instead of
    auth_middleware.require_auth([Scopes.XXX]).
    """
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_WRITE = "workflow:write"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_EXECUTE = "workflow:execute"
    WORKFLOW_CONTROL = "workflow:execute"  # Alias for backward compatibility
    AGENT_READ = "agent:read"
    AGENT_WRITE = "agent:write"
    METRICS_READ = "metrics:read"
    ADMIN = "admin"


# Dependencies for common scope requirements
require_workflow_read = require_scopes(Scopes.WORKFLOW_READ)
require_workflow_write = require_scopes(Scopes.WORKFLOW_WRITE)
require_admin = require_scopes(Scopes.ADMIN)
