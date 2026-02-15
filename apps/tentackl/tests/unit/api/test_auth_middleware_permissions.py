"""Permission enforcement tests for auth_middleware.require_permission."""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.auth_middleware import AuthMiddleware, AuthType, AuthUser


class TestRequirePermission:
    """Verify non-bearer auth does not bypass permission checks."""

    @pytest.mark.asyncio
    async def test_api_key_without_required_scope_is_denied(self):
        middleware = AuthMiddleware()
        dep = middleware.require_permission("events", "publish")

        request = MagicMock()
        request.headers = {"X-API-Key": "test-key"}
        request.state = MagicMock()

        user = AuthUser(
            id="svc-1",
            auth_type=AuthType.API_KEY,
            scopes=["tasks:view"],
            metadata={},
        )

        with patch.object(middleware, "authenticate", new=AsyncMock(return_value=(user, AuthType.API_KEY))):
            with pytest.raises(HTTPException) as exc:
                await dep(request)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_api_key_with_required_scope_is_allowed(self):
        middleware = AuthMiddleware()
        dep = middleware.require_permission("events", "publish")

        request = MagicMock()
        request.headers = {"X-API-Key": "test-key"}
        request.state = MagicMock()

        user = AuthUser(
            id="svc-1",
            auth_type=AuthType.API_KEY,
            scopes=["events:publish"],
            metadata={},
        )

        with patch.object(middleware, "authenticate", new=AsyncMock(return_value=(user, AuthType.API_KEY))):
            result = await dep(request)

        assert result.id == "svc-1"

    @pytest.mark.asyncio
    async def test_bearer_uses_inkpass_permission_check(self):
        middleware = AuthMiddleware()
        dep = middleware.require_permission("events", "admin")

        request = MagicMock()
        request.headers = {"Authorization": "Bearer bearer-token"}
        request.state = MagicMock()

        user = AuthUser(
            id="user-1",
            auth_type=AuthType.BEARER,
            scopes=[],
            metadata={},
        )

        with patch.object(middleware, "authenticate", new=AsyncMock(return_value=(user, AuthType.BEARER))), \
             patch("src.api.auth_middleware.inkpass_check_permission", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await dep(request)

        assert exc.value.status_code == 403
