"""Abstract auth backend interface.

Defines the contract that all auth backends (InkPass, local) must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AuthBackend(ABC):
    """Abstract base class for authentication backends.

    Each backend implements token validation, API key validation,
    permission checking, and optionally user management operations
    (login, register, etc.).
    """

    supports_registration: bool = False
    supports_permissions: bool = False
    supports_user_management: bool = False

    @abstractmethod
    async def validate_token(self, token: str) -> Optional[Any]:
        """Validate a JWT token.

        Args:
            token: JWT access token

        Returns:
            User info object if valid, None if invalid
        """
        ...

    @abstractmethod
    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        """Validate an API key.

        Args:
            api_key: The API key string

        Returns:
            API key info object if valid, None if invalid
        """
        ...

    @abstractmethod
    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if a user has permission for a resource/action.

        Args:
            token: JWT access token
            resource: Resource name (e.g., "workflows", "agents")
            action: Action name (e.g., "read", "write", "execute")
            context: Optional ABAC context

        Returns:
            True if permitted, False otherwise
        """
        ...

    @abstractmethod
    async def login(self, email: str, password: str) -> Optional[Any]:
        """Authenticate a user.

        Args:
            email: User email
            password: User password

        Returns:
            Token response if successful, None otherwise
        """
        ...

    @abstractmethod
    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new user.

        Args:
            email: User email
            password: User password
            organization_name: Optional organization name
            first_name: First name
            last_name: Last name

        Returns:
            Registration response dict
        """
        ...

    @abstractmethod
    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an API key.

        Args:
            token: JWT access token
            name: Key name
            scopes: Optional scopes

        Returns:
            API key response dict
        """
        ...

    @abstractmethod
    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        """Verify email with OTP code.

        Args:
            email: User email
            code: Verification code

        Returns:
            Verification response dict
        """
        ...

    @abstractmethod
    async def resend_verification(self, email: str) -> Dict[str, Any]:
        """Resend email verification code.

        Args:
            email: User email

        Returns:
            Response dict
        """
        ...

    @abstractmethod
    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        """Revoke an API key."""
        ...

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token via backend."""
        ...

    @abstractmethod
    async def forgot_password(self, email: str) -> Dict[str, Any]:
        """Initiate forgot password flow."""
        ...

    @abstractmethod
    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        """Reset password via OTP code."""
        ...

    @abstractmethod
    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        """Update authenticated user profile."""
        ...

    @abstractmethod
    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        """Initiate email change flow."""
        ...

    @abstractmethod
    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        """Confirm email change flow."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the auth backend is healthy.

        Returns:
            True if healthy
        """
        ...
