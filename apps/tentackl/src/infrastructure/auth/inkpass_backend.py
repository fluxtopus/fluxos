# REVIEW: Delegates to clients/inkpass for all operations; no retry/backoff or
# REVIEW: circuit breaking here.
"""InkPass authentication backend.

Wraps the existing src/clients/inkpass module. This is the ONLY file
that imports from inkpass_sdk (via clients/inkpass).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog
from inkpass_sdk.exceptions import (
    AuthenticationError,
    InkPassError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

from .backend import AuthBackend

logger = structlog.get_logger(__name__)


class InkPassAuthBackend(AuthBackend):
    """Authentication backend that delegates to InkPass service.

    All the caching, JWT verification, and Redis logic lives in
    src/clients/inkpass — this backend simply delegates to it.
    """

    supports_registration = True
    supports_permissions = True
    supports_user_management = True

    def __init__(self) -> None:
        # Lazy-import to keep the import boundary here
        from src.clients.inkpass import inkpass_client

        self._inkpass_client = inkpass_client
        logger.info("InkPassAuthBackend initialized")

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from src.core.config import settings

        url = f"{settings.INKPASS_URL}{path}"
        headers = {"Authorization": f"Bearer {token}"} if token else None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=payload,
                    params=params,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise ServiceUnavailableError("InkPass request timed out") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("InkPass request failed") from exc

        detail = None
        if response.content:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text

        if response.status_code >= 400:
            message = str(detail or "InkPass request failed")
            if response.status_code == 401:
                raise AuthenticationError(message)
            if response.status_code == 403:
                raise PermissionDeniedError(message)
            if response.status_code == 404:
                raise ResourceNotFoundError(message)
            if response.status_code in (400, 422):
                raise ValidationError(message)
            if response.status_code in (429, 500, 502, 503, 504):
                raise ServiceUnavailableError(message)
            raise InkPassError(message)

        if not response.content:
            return {}

        try:
            return response.json()
        except Exception:
            return {}

    async def validate_token(self, token: str) -> Optional[Any]:
        from src.clients.inkpass import validate_token

        return await validate_token(token)

    async def validate_api_key(self, api_key: str) -> Optional[Any]:
        from src.clients.inkpass import validate_api_key

        return await validate_api_key(api_key)

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        from src.clients.inkpass import check_permission

        return await check_permission(token, resource, action, context)

    async def login(self, email: str, password: str) -> Optional[Any]:
        from src.clients.inkpass import login

        return await login(email, password)

    async def register_user(
        self,
        email: str,
        password: str,
        organization_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        from src.clients.inkpass import register_user

        return await register_user(
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
        from src.clients.inkpass import create_api_key

        return await create_api_key(token=token, name=name, scopes=scopes)

    async def verify_email(self, email: str, code: str) -> Dict[str, Any]:
        from src.clients.inkpass import verify_email

        return await verify_email(email, code)

    async def resend_verification(self, email: str) -> Dict[str, Any]:
        from src.clients.inkpass import resend_verification

        return await resend_verification(email)

    async def revoke_api_key(self, token: str, api_key: str) -> Dict[str, Any]:
        await self._request_json(
            "DELETE",
            f"/api/v1/api-keys/{api_key}",
            token=token,
        )
        return {"message": "API key revoked successfully"}

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/v1/auth/refresh",
            params={"refresh_token": refresh_token},
        )

    async def forgot_password(self, email: str) -> Dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/v1/auth/forgot-password",
            payload={"email": email},
        )

    async def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/v1/auth/reset-password",
            payload={
                "email": email,
                "code": code,
                "new_password": new_password,
            },
        )

    async def update_profile(
        self,
        token: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if first_name is not None:
            payload["first_name"] = first_name
        if last_name is not None:
            payload["last_name"] = last_name
        return await self._request_json(
            "PATCH",
            "/api/v1/auth/profile",
            token=token,
            payload=payload,
        )

    async def initiate_email_change(self, token: str, new_email: str) -> Dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/v1/auth/email-change/initiate",
            token=token,
            payload={"new_email": new_email},
        )

    async def confirm_email_change(self, token: str, code: str) -> Dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/v1/auth/email-change/confirm",
            token=token,
            payload={"code": code},
        )

    async def health_check(self) -> bool:
        from src.clients.inkpass import health_check

        return await health_check()

    @property
    def client(self):
        """Access the underlying InkPass SDK client (for proxy endpoints)."""
        return self._inkpass_client
