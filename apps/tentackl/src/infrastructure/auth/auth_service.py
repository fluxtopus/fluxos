# REVIEW: Thin wrapper; does not provide any caching or request-scoped context.
"""Unified auth service — the single entry point for authentication.

Picks the backend at startup based on configuration, then delegates
all auth operations. Consumers never know or care whether InkPass
exists or not.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from .backend import AuthBackend

logger = structlog.get_logger(__name__)


class AuthService:
    """Unified auth service. Encapsulates InkPass or local auth."""

    def __init__(self, backend: AuthBackend) -> None:
        self._backend = backend

    async def validate_token(self, token: str) -> Optional[Any]:
        return await self._backend.validate_token(token)

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        return await self._backend.validate_api_key(api_key)

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self._backend.check_permission(token, resource, action, context)

    async def login(self, email: str, password: str) -> Optional[Any]:
        return await self._backend.login(email, password)

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._backend.register_user(
            email=email,
            password=password,
            organization_name=organization_name,
            first_name=first_name,
            last_name=last_name,
        )

    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await self._backend.create_api_key(token=token, name=name, scopes=scopes)

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        return await self._backend.verify_email(email, code)

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        return await self._backend.resend_verification(email)

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        return await self._backend.revoke_api_key(token, api_key)

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        return await self._backend.refresh_access_token(refresh_token)

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        return await self._backend.forgot_password(email)

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        return await self._backend.reset_password(email, code, new_password)

    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        return await self._backend.update_profile(token, first_name, last_name)

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        return await self._backend.initiate_email_change(token, new_email)

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        return await self._backend.confirm_email_change(token, code)

    async def health_check(self) -> bool:
        return await self._backend.health_check()

    @property
    def supports_registration(self) -> bool:
        """Whether this backend supports user registration."""
        return self._backend.supports_registration

    @property
    def supports_permissions(self) -> bool:
        """Whether this backend supports ABAC permission checks."""
        return self._backend.supports_permissions

    @property
    def supports_user_management(self) -> bool:
        """Whether this backend supports login/register/verify flows."""
        return self._backend.supports_user_management

    @property
    def backend(self) -> AuthBackend:
        """Access the underlying backend (for advanced use like proxy endpoints)."""
        return self._backend
