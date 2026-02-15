"""Domain ports for authentication operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class AuthOperationsPort(Protocol):
    """Port for auth operations used by API/application layers."""

    async def validate_token(self, token: str) -> Optional[Any]:
        ...

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        ...

    async def login(self, email: str, password: str) -> Optional[Any]:
        ...

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        ...

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        ...

    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        ...

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        ...

    @property
    def supports_user_management(self) -> bool:
        ...

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        ...

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        ...

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        ...

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        ...

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        ...

    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        ...

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        ...

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        ...
