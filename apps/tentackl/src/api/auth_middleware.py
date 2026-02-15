# REVIEW:
# - Overlaps with auth.py; two JWT/auth implementations create ambiguity and drift risk.
# - SECRET_KEY/REDIS_URL read from env at import time (bypasses settings; hard to override in tests).
# - AuthUser.scopes and AuthUser.metadata use mutable defaults; should be default_factory.
# - Auth uses inkPass permissions for bearer tokens but falls back to scopes for API keys/webhooks; mixed model is confusing.
"""Enhanced authentication middleware for the API."""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, APIKeyHeader
from fastapi.security.utils import get_authorization_scheme_param
import jwt
from jwt import exceptions as jwt_exceptions
import hashlib
import hmac
import json
import structlog
from pydantic import BaseModel, Field
import redis.asyncio as redis_async
from src.core.config import settings
from src.application.auth import AuthUseCases
from src.infrastructure.auth import AuthServiceAdapter
from src.api.token_cache import token_cache
from src.database.api_key_repository import APIKeyRepository
from src.interfaces.database import Database

logger = structlog.get_logger()

# Configuration from environment — no insecure fallback (SEC-003)
SECRET_KEY = os.getenv("TENTACKL_SECRET_KEY") or settings.SECRET_KEY or ""
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TENTACKL_TOKEN_EXPIRE_MINUTES", "30"))
API_KEY_HEADER = "X-API-Key"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


class AuthType:
    """Authentication types."""
    BEARER = "bearer"
    API_KEY = "api_key"
    WEBHOOK = "webhook"
    NONE = "none"


class AuthUser(BaseModel):
    """Authenticated user/service model."""
    id: str
    auth_type: str
    username: Optional[str] = None
    service_name: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuthMiddleware:
    """
    Enhanced authentication middleware supporting multiple auth methods.
    
    Features:
    - JWT Bearer tokens
    - API Keys with Redis caching
    - Webhook signature validation
    - Scope-based authorization
    - Rate limiting integration
    """
    
    def __init__(self):
        pass

    async def _new_redis(self) -> redis_async.Redis:
        """Create a new Redis client instance.

        Avoids cross-event-loop reuse issues in tests by not caching
        the client object across requests.
        """
        return await redis_async.from_url(REDIS_URL, decode_responses=True)

    async def _get_webhook_secret(self, source: str) -> Optional[str]:
        """Look up the HMAC secret for a webhook source.

        Checks Redis for the source's authentication config using the same
        key pattern as EventGateway (``tentackl:gateway:source:<source>``).
        Falls back to the ``WEBHOOK_SECRET_<SOURCE>`` environment variable
        (uppercased, hyphens replaced with underscores) and finally
        ``WEBHOOK_SECRET`` as a global default.

        Returns ``None`` when no secret can be found.
        """
        # 1. Try Redis (EventGateway key space)
        try:
            redis_client = await self._new_redis()
            try:
                source_key = f"tentackl:gateway:source:{source}"
                auth_data = await redis_client.hget(source_key, "authentication")
                if auth_data:
                    auth_config = json.loads(auth_data)
                    secret = auth_config.get("secret")
                    if secret:
                        return secret
            finally:
                await redis_client.aclose()
        except Exception as e:
            logger.debug(
                "Redis lookup for webhook secret failed, trying env vars",
                source=source,
                error=str(e),
            )

        # 2. Per-source env var: WEBHOOK_SECRET_<SOURCE>
        env_key = f"WEBHOOK_SECRET_{source.upper().replace('-', '_')}"
        secret = os.getenv(env_key)
        if secret:
            return secret

        # 3. Global fallback env var
        return os.getenv("WEBHOOK_SECRET")

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Verify webhook signature using HMAC."""
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    async def authenticate(self, request: Request) -> Tuple[Optional[AuthUser], str]:
        """
        Authenticate request using multiple methods.

        Returns:
            Tuple of (AuthUser or None, auth_type)
        """
        # Try Bearer token first (using inkPass for validation)
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, token = get_authorization_scheme_param(authorization)
            if scheme.lower() == "bearer" and token:
                try:
                    # Check cache first to reduce InkPass traffic.
                    cached_user = await token_cache.get(token)
                    if cached_user:
                        user = AuthUser(
                            id=cached_user.get("id", ""),
                            auth_type=AuthType.BEARER,
                            username=cached_user.get("email") or cached_user.get("username"),
                            scopes=cached_user.get("scopes", []),
                            metadata=cached_user,
                        )
                        return user, AuthType.BEARER

                    # Validate token with inkPass
                    inkpass_user = await inkpass_validate_token(token)

                    if inkpass_user:
                        # Convert inkPass user to AuthUser
                        user = AuthUser(
                            id=inkpass_user.id,
                            auth_type=AuthType.BEARER,
                            username=inkpass_user.email,  # Use email as username
                            scopes=[],  # Permissions are handled via inkPass, not scopes
                            metadata={
                                "email": inkpass_user.email,
                                "first_name": inkpass_user.first_name,
                                "last_name": inkpass_user.last_name,
                                "organization_id": inkpass_user.organization_id,
                                "two_fa_enabled": inkpass_user.two_fa_enabled,
                                "status": inkpass_user.status,
                                "inkpass_validated": True,
                                "token": token,  # Store token for permission checks
                            }
                        )
                        await token_cache.set(
                            token,
                            {
                                "id": user.id,
                                "email": inkpass_user.email,
                                "first_name": inkpass_user.first_name,
                                "last_name": inkpass_user.last_name,
                                "organization_id": inkpass_user.organization_id,
                                "two_fa_enabled": inkpass_user.two_fa_enabled,
                                "status": inkpass_user.status,
                                "inkpass_validated": True,
                                "token": token,
                                "scopes": [],
                            },
                        )

                        logger.debug(
                            "Token validated via inkPass",
                            user_id=user.id,
                            email=inkpass_user.email,
                            organization_id=inkpass_user.organization_id
                        )

                        return user, AuthType.BEARER
                    else:
                        # Token is invalid
                        logger.warning("Token validation failed via inkPass")
                        from fastapi import HTTPException as _HTTPException
                        raise _HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Could not validate credentials"
                        )

                except HTTPException:
                    # Re-raise HTTP exceptions
                    raise
                except Exception as e:
                    logger.warning(f"Token validation error: {e}")
                    from fastapi import HTTPException as _HTTPException
                    raise _HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Could not validate credentials"
                    )
        
        # Try API Key (validated via InkPass)
        api_key = request.headers.get(API_KEY_HEADER)
        if api_key:
            api_key_info = await inkpass_validate_api_key(api_key)
            if api_key_info:
                user = AuthUser(
                    id=api_key_info.user_id or api_key_info.id,
                    auth_type=AuthType.API_KEY,
                    scopes=api_key_info.scopes,
                    metadata={
                        "organization_id": api_key_info.organization_id,
                        "api_key_id": api_key_info.id,
                        "api_key_name": api_key_info.name,
                        "inkpass_validated": True,
                    },
                )

                logger.debug(
                    "API key validated via inkPass",
                    key_id=api_key_info.id,
                    organization_id=api_key_info.organization_id,
                )

                return user, AuthType.API_KEY
        
        # Try webhook signature (for specific endpoints)
        webhook_signature = request.headers.get("X-Webhook-Signature")
        webhook_source = request.headers.get("X-Webhook-Source")
        if webhook_signature and webhook_source:
            # Look up the webhook secret for this source and validate the signature
            try:
                secret = await self._get_webhook_secret(webhook_source)
                if not secret:
                    logger.warning(
                        "Webhook source has no secret configured",
                        source=webhook_source
                    )
                    return None, AuthType.NONE

                # Read the raw request body for signature verification
                body = await request.body()
                if not self.verify_webhook_signature(body, webhook_signature, secret):
                    logger.warning(
                        "Webhook signature verification failed",
                        source=webhook_source
                    )
                    return None, AuthType.NONE

                user = AuthUser(
                    id=f"webhook_{webhook_source}",
                    auth_type=AuthType.WEBHOOK,
                    service_name=webhook_source,
                    scopes=["webhook:publish"],
                    metadata={"source": webhook_source, "signature_verified": True}
                )

                logger.debug(
                    "Webhook signature verified",
                    source=webhook_source
                )
                return user, AuthType.WEBHOOK

            except Exception as e:
                logger.error(
                    "Webhook signature verification error",
                    source=webhook_source,
                    error=str(e)
                )
                return None, AuthType.NONE
        
        # No authentication
        return None, AuthType.NONE
    
    def require_auth(self):
        """
        Dependency to require authentication only (no authorization).

        For authorization, use require_permission() which checks via InkPass.

        Usage:
            @app.get("/api/resource")
            async def get_resource(user: AuthUser = Depends(auth_middleware.require_auth())):
                ...
        """
        async def auth_dependency(request: Request) -> AuthUser:
            user, auth_type = await self.authenticate(request)

            if not user:
                # Optional development bypass only when explicitly enabled (SEC-010 hardened)
                from src.core.config import is_dev_auth_bypass_allowed
                dev_bypass = is_dev_auth_bypass_allowed()
                if dev_bypass:
                    user = AuthUser(
                        id="dev",
                        auth_type=AuthType.NONE,
                        username="developer",
                        scopes=[],
                        metadata={"auto_dev_user": True}
                    )
                    logger.info("Dev auth bypass active: injecting developer user")
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            # Add auth info to request state
            request.state.auth_user = user
            request.state.auth_type = auth_type

            return user

        return auth_dependency
    
    def optional_auth(self):
        """
        Dependency for optional authentication.

        Sets request.state.auth_user if authenticated, otherwise None.
        """
        async def auth_dependency(request: Request) -> Optional[AuthUser]:
            user, auth_type = await self.authenticate(request)

            request.state.auth_user = user
            request.state.auth_type = auth_type if user else AuthType.NONE

            return user

        return auth_dependency

    def _scope_grants_permission(
        self,
        scopes: Optional[List[str]],
        resource: str,
        action: str,
    ) -> bool:
        """Check whether provided scopes grant resource/action access."""
        if not scopes:
            return False

        resource_l = resource.lower()
        action_l = action.lower()
        accepted = {
            f"{resource_l}:{action_l}",
            f"{resource_l}:*",
            f"*:{action_l}",
            "*:*",
            "admin",
            f"{resource_l}.{action_l}",
            f"{resource_l}.*",
        }
        return any((scope or "").strip().lower() in accepted for scope in scopes)

    def require_permission(self, resource: str, action: str, context: Optional[Dict[str, Any]] = None):
        """
        Dependency to require specific permission via inkPass.

        This checks permissions using inkPass's ABAC system.
        Only works with Bearer tokens validated by inkPass.

        Args:
            resource: Resource name (e.g., "workflows", "agents")
            action: Action name (e.g., "read", "write", "execute")
            context: Optional ABAC context

        Usage:
            @app.post("/api/workflows", dependencies=[auth_middleware.require_permission("workflows", "create")])
        """
        async def permission_dependency(request: Request) -> AuthUser:
            # First authenticate the user
            user, auth_type = await self.authenticate(request)

            if not user:
                # Optional development bypass only when explicitly enabled (SEC-010 hardened)
                from src.core.config import is_dev_auth_bypass_allowed
                dev_bypass = is_dev_auth_bypass_allowed()
                if dev_bypass:
                    user = AuthUser(
                        id="dev",
                        auth_type=AuthType.NONE,
                        username="developer",
                        scopes=[],
                        metadata={"auto_dev_user": True}
                    )
                    auth_type = AuthType.NONE
                    logger.info("Dev auth bypass active: injecting developer user")
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            # Dev bypass user has full access in explicitly allowed development mode.
            if user.metadata.get("auto_dev_user"):
                request.state.auth_user = user
                request.state.auth_type = auth_type
                return user

            # Bearer tokens use inkPass ABAC checks.
            if auth_type == AuthType.BEARER:
                # Extract token from request
                authorization = request.headers.get("Authorization")
                if not authorization:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                scheme, token = get_authorization_scheme_param(authorization)
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                # Check permission with inkPass
                has_permission = await inkpass_check_permission(
                    token=token,
                    resource=resource,
                    action=action,
                    context=context,
                )

                if not has_permission:
                    logger.warning(
                        "Permission denied via inkPass",
                        user_id=user.id,
                        resource=resource,
                        action=action
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission denied: {resource}:{action}"
                    )

                logger.debug(
                    "Permission granted via inkPass",
                    user_id=user.id,
                    resource=resource,
                    action=action
                )
            else:
                # API keys/webhooks require explicit scope grants.
                has_scope = self._scope_grants_permission(
                    scopes=user.scopes,
                    resource=resource,
                    action=action,
                )
                if not has_scope:
                    logger.warning(
                        "Permission denied via scopes",
                        user_id=user.id,
                        auth_type=auth_type,
                        resource=resource,
                        action=action,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission denied: {resource}:{action}"
                    )
                logger.debug(
                    "Permission granted via scopes",
                    user_id=user.id,
                    auth_type=auth_type,
                    resource=resource,
                    action=action,
                )

            # Add auth info to request state
            request.state.auth_user = user
            request.state.auth_type = auth_type

            return user

        return permission_dependency

    # ------------------------------------------------------------------
    # Compatibility helpers used by older tests and non-router consumers.
    # ------------------------------------------------------------------

    async def create_api_key(
        self,
        service_name: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create an API key using durable storage."""
        import secrets

        api_key = f"tentackl_{secrets.token_urlsafe(32)}"
        repository = APIKeyRepository(Database())
        success = await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=scopes or [],
            expires_in_days=expires_in_days,
            created_by=created_by,
            metadata=metadata,
        )
        return api_key if success else None

    async def validate_api_key(self, api_key: str):
        """Validate an API key using durable storage."""
        repository = APIKeyRepository(Database())
        return await repository.validate_api_key(api_key)

    async def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key using durable storage."""
        repository = APIKeyRepository(Database())
        return await repository.revoke_api_key(api_key)


# Global middleware instance
auth_middleware = AuthMiddleware()
_auth_use_cases: Optional[AuthUseCases] = None


def get_auth_use_cases() -> AuthUseCases:
    """Resolve shared auth use cases for middleware helper operations."""
    global _auth_use_cases
    if _auth_use_cases is None:
        _auth_use_cases = AuthUseCases(auth_ops=AuthServiceAdapter())
    return _auth_use_cases


# -----------------------------------------------------------------------------
# InkPass helpers (module-level for easy patching in tests)
# -----------------------------------------------------------------------------


async def inkpass_validate_token(token: str):
    """Validate a bearer token via InkPass."""
    return await get_auth_use_cases().validate_token(token)


async def inkpass_validate_api_key(api_key: str):
    """Validate an API key via InkPass."""
    return await get_auth_use_cases().validate_api_key(api_key)


async def inkpass_check_permission(
    token: str,
    resource: str,
    action: str,
    context: Optional[Dict[str, Any]] = None,
):
    """Check a permission via InkPass."""
    return await get_auth_use_cases().check_permission(
        token=token,
        resource=resource,
        action=action,
        context=context,
    )


# Convenience functions
async def create_access_token(
    user_id: str,
    username: Optional[str] = None,
    scopes: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": user_id,
        "username": username,
        "scopes": scopes or [],
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Note: Scopes system has been removed. All permission checking now uses InkPass.
# Use auth_middleware.require_permission("resource", "action") for authorization.
# For API keys, use auth_middleware.require_auth() for authentication only.

# Re-export Scopes from auth.py for backward compatibility with CLI and other tools
from src.api.auth import Scopes

# Scope sets for backward compatibility (used by CLI and auth_management)
READONLY_SCOPES = [Scopes.WORKFLOW_READ, Scopes.AGENT_READ, Scopes.METRICS_READ]
OPERATOR_SCOPES = READONLY_SCOPES + [Scopes.WORKFLOW_EXECUTE]
DEVELOPER_SCOPES = OPERATOR_SCOPES + [Scopes.WORKFLOW_WRITE, Scopes.AGENT_WRITE]
ADMIN_SCOPES = DEVELOPER_SCOPES + [Scopes.WORKFLOW_DELETE, Scopes.ADMIN]
