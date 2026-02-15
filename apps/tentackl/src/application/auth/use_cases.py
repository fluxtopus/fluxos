"""Application use cases for authentication operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.domain.auth import AuthOperationsPort


@dataclass
class AuthUseCases:
    """Application-layer orchestration for auth flows."""

    auth_ops: AuthOperationsPort

    async def validate_token(self, token: str) -> Optional[Any]:
        return await self.auth_ops.validate_token(token)

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        return await self.auth_ops.validate_api_key(api_key)

    async def login(self, email: str, password: str) -> Optional[Any]:
        return await self.auth_ops.login(email=email, password=password)

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.auth_ops.register_user(
            email=email,
            password=password,
            organization_name=organization_name,
            first_name=first_name,
            last_name=last_name,
        )

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        return await self.auth_ops.verify_email(email=email, code=code)

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        return await self.auth_ops.resend_verification(email=email)

    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await self.auth_ops.create_api_key(token=token, name=name, scopes=scopes)

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self.auth_ops.check_permission(
            token=token,
            resource=resource,
            action=action,
            context=context,
        )

    @property
    def supports_user_management(self) -> bool:
        return self.auth_ops.supports_user_management

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        return await self.auth_ops.get_user_info(token=token)

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        return await self.auth_ops.revoke_api_key(token=token, api_key=api_key)

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        return await self.auth_ops.refresh_access_token(refresh_token=refresh_token)

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        return await self.auth_ops.forgot_password(email=email)

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        return await self.auth_ops.reset_password(
            email=email,
            code=code,
            new_password=new_password,
        )

    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        return await self.auth_ops.update_profile(
            token=token,
            first_name=first_name,
            last_name=last_name,
        )

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        return await self.auth_ops.initiate_email_change(token=token, new_email=new_email)

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        return await self.auth_ops.confirm_email_change(token=token, code=code)
