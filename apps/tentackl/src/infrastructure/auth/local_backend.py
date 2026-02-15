# REVIEW: Relies on TENTACKL_API_KEY and TENTACKL_SECRET_KEY env vars;
# REVIEW: no rotation or revocation support.
"""Local authentication backend for standalone mode.

Provides JWT validation using TENTACKL_SECRET_KEY and API key
validation using TENTACKL_API_KEY. No external dependencies.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog

from .backend import AuthBackend

logger = structlog.get_logger(__name__)


class _LocalUser:
    """Minimal user-like object returned by local token validation.

    Mimics the subset of fields that auth_middleware expects from
    inkpass_sdk.models.UserResponse so the middleware can construct
    an AuthUser without changes.
    """

    def __init__(
        self,
        id: str,
        email: str,
        organization_id: str = "local",
        status: str = "active",
        two_fa_enabled: bool = False,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.status = status
        self.two_fa_enabled = two_fa_enabled
        self.first_name = first_name
        self.last_name = last_name


class _LocalAPIKeyInfo:
    """Minimal API-key-info object returned by local API key validation.

    Mimics inkpass_sdk.models.APIKeyInfoResponse.
    """

    def __init__(
        self,
        id: str,
        user_id: str,
        name: str,
        scopes: List[str],
        organization_id: str = "local",
    ):
        self.id = id
        self.user_id = user_id
        self.name = name
        self.scopes = scopes
        self.organization_id = organization_id


class LocalAuthBackend(AuthBackend):
    """Standalone authentication backend with no external dependencies.

    - Validates JWTs using TENTACKL_SECRET_KEY (reuses src/api/auth.decode_token)
    - Validates API keys by comparing against TENTACKL_API_KEY env var
    - All authenticated users are authorized (no permission checks)
    """

    supports_registration = False
    supports_permissions = False
    supports_user_management = False

    def __init__(self) -> None:
        self._api_key = os.getenv("TENTACKL_API_KEY", "")
        logger.info(
            "LocalAuthBackend initialized",
            has_api_key=bool(self._api_key),
        )

    async def validate_token(self, token: str) -> Optional[Any]:
        """Decode JWT locally using TENTACKL_SECRET_KEY."""
        try:
            from src.api.auth import decode_token

            payload = decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return None

            return _LocalUser(
                id=user_id,
                email=payload.get("email", payload.get("username", user_id)),
                organization_id=payload.get("organization_id", "local"),
                first_name=payload.get("first_name"),
                last_name=payload.get("last_name"),
            )
        except Exception:
            return None

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        """Compare against TENTACKL_API_KEY env var."""
        if not self._api_key:
            logger.debug("No TENTACKL_API_KEY configured, rejecting API key")
            return None

        if api_key != self._api_key:
            return None

        return _LocalAPIKeyInfo(
            id="local-api-key",
            user_id="api-key-user",
            name="Local API Key",
            scopes=["admin"],
            organization_id="local",
        )

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """In standalone mode, authenticated == authorized."""
        return True

    async def login(self, email: str, password: str) -> Optional[Any]:
        """Login is not supported in standalone mode."""
        raise NotImplementedError(
            "Login is not supported in standalone mode. "
            "Use API keys or pre-generated JWT tokens."
        )

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registration is not supported in standalone mode."""
        raise NotImplementedError(
            "User registration is not supported in standalone mode."
        )

    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """API key creation is not supported in standalone mode."""
        raise NotImplementedError(
            "API key creation is not supported in standalone mode. "
            "Set TENTACKL_API_KEY environment variable instead."
        )

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        """Email verification is not supported in standalone mode."""
        raise NotImplementedError(
            "Email verification is not supported in standalone mode."
        )

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        """Resend verification is not supported in standalone mode."""
        raise NotImplementedError(
            "Email verification is not supported in standalone mode."
        )

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "API key revocation is not supported in standalone mode."
        )

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "Token refresh is not supported in standalone mode."
        )

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "Forgot password is not supported in standalone mode."
        )

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "Password reset is not supported in standalone mode."
        )

    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "Profile updates are not supported in standalone mode."
        )

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "Email change is not supported in standalone mode."
        )

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "Email change is not supported in standalone mode."
        )

    async def health_check(self) -> bool:
        """Local backend is always healthy."""
        return True
