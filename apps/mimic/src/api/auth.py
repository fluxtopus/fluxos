"""
Mimic InkPass Authentication Dependencies.

Provides FastAPI dependencies for JWT and API key authentication
via InkPass Mothership service.
"""

from dataclasses import dataclass
from typing import Annotated, Callable, Optional

import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings

logger = structlog.get_logger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthContext:
    """Authentication context for protected routes."""

    user_id: str
    email: str
    organization_id: str
    auth_type: str  # "jwt" or "api_key"
    token: str  # Original token for permission checks


class InkPassClient:
    """Client for InkPass Mothership authentication service."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def validate_token(self, token: str) -> Optional[dict]:
        """Validate a JWT token via InkPass."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error("inkpass_token_validation_failed", error=str(e))
            return None

    async def validate_api_key(self, api_key: str) -> Optional[dict]:
        """Validate an API key via InkPass."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/auth/api-key/validate",
                    headers={"X-API-Key": api_key},
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error("inkpass_api_key_validation_failed", error=str(e))
            return None

    async def check_permission(
        self, token: str, resource: str, action: str
    ) -> bool:
        """Check if user has a specific permission.

        Uses the /api/v1/auth/check endpoint which checks permissions
        via the role template system.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/check",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"resource": resource, "action": action},
                    json={},  # ABAC context (optional)
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("has_permission", False)
                return False
        except Exception as e:
            logger.error(
                "inkpass_permission_check_failed",
                error=str(e),
                resource=resource,
                action=action,
            )
            return False


# Singleton for InkPass client
_inkpass_client: Optional[InkPassClient] = None


def get_inkpass_client() -> InkPassClient:
    """Get InkPass client (singleton)."""
    global _inkpass_client

    if _inkpass_client is None:
        _inkpass_client = InkPassClient(base_url=settings.INKPASS_URL)

    return _inkpass_client


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    api_key: Annotated[Optional[str], Depends(api_key_header)],
) -> AuthContext:
    """
    Validate authentication and return user context.

    Supports JWT tokens, API keys via InkPass, and service API keys for internal services.
    """
    inkpass = get_inkpass_client()

    # Try service API key first (for internal service-to-service communication)
    # This allows services like InkPass to call Mimic without going through InkPass validation
    if credentials and settings.MIMIC_SERVICE_API_KEY:
        if credentials.credentials == settings.MIMIC_SERVICE_API_KEY:
            logger.debug("service_api_key_auth", auth_type="service")
            return AuthContext(
                user_id="service:internal",
                email="service@internal",
                organization_id="internal",
                auth_type="service",
                token=credentials.credentials,
            )

    # Try JWT via InkPass
    if credentials:
        user_data = await inkpass.validate_token(credentials.credentials)
        if user_data:
            return AuthContext(
                user_id=user_data.get("id", ""),
                email=user_data.get("email", ""),
                organization_id=user_data.get("organization_id", ""),
                auth_type="jwt",
                token=credentials.credentials,
            )

    # Try API key via InkPass
    if api_key:
        key_data = await inkpass.validate_api_key(api_key)
        if key_data:
            return AuthContext(
                user_id=key_data.get("user_id", ""),
                email="",
                organization_id=key_data.get("organization_id", ""),
                auth_type="api_key",
                token=api_key,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    api_key: Annotated[Optional[str], Depends(api_key_header)],
) -> Optional[AuthContext]:
    """
    Optionally validate authentication.

    Returns None if no valid auth provided (doesn't raise exception).
    """
    inkpass = get_inkpass_client()

    # Try JWT first
    if credentials:
        user_data = await inkpass.validate_token(credentials.credentials)
        if user_data:
            return AuthContext(
                user_id=user_data.get("id", ""),
                email=user_data.get("email", ""),
                organization_id=user_data.get("organization_id", ""),
                auth_type="jwt",
                token=credentials.credentials,
            )

    # Try API key
    if api_key:
        key_data = await inkpass.validate_api_key(api_key)
        if key_data:
            return AuthContext(
                user_id=key_data.get("user_id", ""),
                email="",
                organization_id=key_data.get("organization_id", ""),
                auth_type="api_key",
                token=api_key,
            )

    return None


def require_permission(resource: str, action: str) -> Callable:
    """
    Dependency factory for permission checking.

    Usage:
        @router.get("/notifications")
        async def list_notifications(
            auth: AuthContext = Depends(require_permission("notifications", "view"))
        ):
            ...
    """

    async def checker(
        auth: Annotated[AuthContext, Depends(get_current_user)],
    ) -> AuthContext:
        # Service auth type bypasses permission checks (internal service-to-service)
        if auth.auth_type == "service":
            logger.debug(
                "service_permission_bypass",
                resource=resource,
                action=action,
            )
            return auth

        inkpass = get_inkpass_client()

        # Check permission via InkPass
        has_permission = await inkpass.check_permission(
            token=auth.token,
            resource=resource,
            action=action,
        )

        if not has_permission:
            logger.warning(
                "permission_denied",
                user_id=auth.user_id,
                resource=resource,
                action=action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}",
            )

        return auth

    return checker


# Type aliases for cleaner route signatures
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]
OptionalUser = Annotated[Optional[AuthContext], Depends(get_optional_user)]
