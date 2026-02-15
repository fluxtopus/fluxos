"""Infrastructure adapter for auth operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.auth import AuthOperationsPort
from src.infrastructure.auth.runtime import auth_service
from src.infrastructure.auth.inkpass_backend import InkPassAuthBackend


class AuthServiceAdapter(AuthOperationsPort):
    """Adapter exposing auth_service via AuthOperationsPort."""

    async def validate_token(self, token: str) -> Optional[Any]:
        return await auth_service.validate_token(token)

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        return await auth_service.validate_api_key(api_key)

    async def login(self, email: str, password: str) -> Optional[Any]:
        return await auth_service.login(email=email, password=password)

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await auth_service.register_user(
            email=email,
            password=password,
            organization_name=organization_name,
            first_name=first_name,
            last_name=last_name,
        )

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        return await auth_service.verify_email(email=email, code=code)

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        return await auth_service.resend_verification(email=email)

    async def create_api_key(
        self,
        token: str,
        name: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await auth_service.create_api_key(token=token, name=name, scopes=scopes)

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await auth_service.check_permission(
            token=token,
            resource=resource,
            action=action,
            context=context,
        )

    @property
    def supports_user_management(self) -> bool:
        return auth_service.supports_user_management

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        if not auth_service.supports_user_management:
            return None

        backend = auth_service.backend
        if not isinstance(backend, InkPassAuthBackend):
            return None

        user = await backend.client.get_user_info(token)
        if not user:
            return None

        return {
            "first_name": getattr(user, "first_name", None),
            "last_name": getattr(user, "last_name", None),
            "email": getattr(user, "email", None),
        }

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        return await auth_service.revoke_api_key(token=token, api_key=api_key)

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        return await auth_service.refresh_access_token(refresh_token=refresh_token)

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        return await auth_service.forgot_password(email=email)

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        return await auth_service.reset_password(
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
        return await auth_service.update_profile(
            token=token,
            first_name=first_name,
            last_name=last_name,
        )

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        return await auth_service.initiate_email_change(token=token, new_email=new_email)

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        return await auth_service.confirm_email_change(token=token, code=code)
