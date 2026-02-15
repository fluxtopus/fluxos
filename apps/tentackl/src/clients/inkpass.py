"""inkPass authentication client for Tentackl.

This module provides a singleton inkPass client for authentication and authorization
throughout the Tentackl application.
"""

import hashlib
import inspect
import json
import os
import time
from typing import Optional, Dict, Any, List, Tuple

import jwt
from jwt import exceptions as jwt_exceptions
import redis.asyncio as redis_async
import structlog
from inkpass_sdk import InkPassClient, InkPassConfig
from inkpass_sdk.models import APIKeyInfoResponse, UserResponse, TokenResponse, PermissionCheckResponse
from inkpass_sdk.exceptions import (
    InkPassError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
)
from fastapi import HTTPException, status

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Configuration from environment
INKPASS_URL = os.getenv("INKPASS_URL", "http://inkpass:8000")
INKPASS_TIMEOUT = float(os.getenv("INKPASS_TIMEOUT", "10.0"))
INKPASS_MAX_RETRIES = int(os.getenv("INKPASS_MAX_RETRIES", "3"))
INKPASS_CACHE_ENABLED = os.getenv("INKPASS_CACHE_ENABLED", "true").lower() == "true"
INKPASS_TOKEN_CACHE_TTL_SECONDS = int(os.getenv("INKPASS_TOKEN_CACHE_TTL_SECONDS", "300"))
INKPASS_PERMISSION_CACHE_TTL_SECONDS = int(os.getenv("INKPASS_PERMISSION_CACHE_TTL_SECONDS", "60"))
INKPASS_JWT_SECRET = os.getenv("INKPASS_JWT_SECRET", "")
INKPASS_JWT_PUBLIC_KEY = os.getenv("INKPASS_JWT_PUBLIC_KEY", "")
INKPASS_JWT_ALGORITHM = os.getenv("INKPASS_JWT_ALGORITHM", "HS256")
INKPASS_JWT_ISSUER = os.getenv("INKPASS_JWT_ISSUER", "")
INKPASS_JWT_AUDIENCE = os.getenv("INKPASS_JWT_AUDIENCE", "")
INKPASS_JWT_LEEWAY_SECONDS = int(os.getenv("INKPASS_JWT_LEEWAY_SECONDS", "30"))
INKPASS_REVOCATION_ENABLED = os.getenv("INKPASS_REVOCATION_ENABLED", "false").lower() == "true"
INKPASS_LOCAL_TOKEN_CACHE_MAX = int(os.getenv("INKPASS_LOCAL_TOKEN_CACHE_MAX", "1024"))

# Initialize inkPass SDK configuration
inkpass_config = InkPassConfig(
    base_url=INKPASS_URL,
    timeout=INKPASS_TIMEOUT,
    max_retries=INKPASS_MAX_RETRIES,
    verify_ssl=True,
)

# Create singleton client instance
inkpass_client = InkPassClient(inkpass_config)

logger.info(
    "inkPass client initialized",
    base_url=INKPASS_URL,
    timeout=INKPASS_TIMEOUT,
    max_retries=INKPASS_MAX_RETRIES,
)

_LOCAL_TOKEN_CACHE: Dict[str, Tuple[int, Dict[str, Any]]] = {}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _inkpass_verify_key() -> Optional[str]:
    if INKPASS_JWT_PUBLIC_KEY:
        return INKPASS_JWT_PUBLIC_KEY
    if INKPASS_JWT_SECRET:
        return INKPASS_JWT_SECRET
    return None


def _decode_token_local(token: str) -> Optional[Dict[str, Any]]:
    key = _inkpass_verify_key()
    if not key:
        return None

    options = {
        "verify_aud": bool(INKPASS_JWT_AUDIENCE),
        "verify_iss": bool(INKPASS_JWT_ISSUER),
    }
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[INKPASS_JWT_ALGORITHM],
            audience=INKPASS_JWT_AUDIENCE or None,
            issuer=INKPASS_JWT_ISSUER or None,
            leeway=INKPASS_JWT_LEEWAY_SECONDS,
            options=options,
        )
    except jwt_exceptions.PyJWTError as e:
        logger.debug("Local inkPass token validation failed", error=str(e))
        return None


def _decode_token_unverified(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
    except jwt_exceptions.PyJWTError:
        return None


def _token_ttl_seconds(token: str) -> Optional[int]:
    claims = _decode_token_unverified(token)
    if not claims:
        return None
    exp = claims.get("exp")
    try:
        exp_seconds = int(exp)
    except (TypeError, ValueError):
        return None
    ttl = exp_seconds - int(time.time())
    if ttl <= 0:
        return None
    return ttl


def _claims_to_user_response(claims: Dict[str, Any]) -> Optional[UserResponse]:
    user_id = claims.get("sub")
    email = claims.get("email")
    organization_id = claims.get("organization_id")
    if not user_id or not email or not organization_id:
        return None

    return UserResponse(
        id=user_id,
        email=email,
        organization_id=organization_id,
        status=claims.get("status", "active"),
        two_fa_enabled=claims.get("two_fa_enabled", False),
    )


def _cache_enabled() -> bool:
    return INKPASS_CACHE_ENABLED and bool(REDIS_URL)


async def _new_redis() -> redis_async.Redis:
    client = redis_async.from_url(REDIS_URL, decode_responses=True)
    if inspect.isawaitable(client):
        client = await client
    return client


async def _cache_get(key: str) -> Optional[str]:
    if not _cache_enabled():
        return None
    redis_client = await _new_redis()
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.warning("inkPass cache read failed", key=key, error=str(e))
        return None
    finally:
        await redis_client.close()


async def _cache_set(key: str, value: str, ttl_seconds: int) -> None:
    if not _cache_enabled() or ttl_seconds <= 0:
        return
    redis_client = await _new_redis()
    try:
        await redis_client.setex(key, ttl_seconds, value)
    except Exception as e:
        logger.warning("inkPass cache write failed", key=key, error=str(e))
    finally:
        await redis_client.close()


async def _is_token_revoked(token: str) -> bool:
    if not INKPASS_REVOCATION_ENABLED or not REDIS_URL:
        return False
    redis_client = await _new_redis()
    token_key = f"inkpass:revoked:{_token_hash(token)}"
    try:
        return await redis_client.exists(token_key) > 0
    except Exception as e:
        logger.warning("inkPass revocation check failed", error=str(e))
        return False
    finally:
        await redis_client.close()


def _permission_cache_key(
    token: str,
    resource: str,
    action: str,
    context: Optional[Dict[str, Any]]
) -> str:
    token_key = _token_hash(token)
    if context:
        context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
        context_key = hashlib.sha256(context_json.encode()).hexdigest()
    else:
        context_key = "none"
    return f"inkpass:perm:{token_key}:{resource}:{action}:{context_key}"


def _token_cache_key(token: str) -> str:
    return f"inkpass:token:{_token_hash(token)}"


def _cap_ttl(default_ttl: int, token_ttl: Optional[int]) -> int:
    if token_ttl is None:
        return default_ttl
    return min(default_ttl, token_ttl)


def _local_cache_get(token: str) -> Optional[Dict[str, Any]]:
    key = _token_hash(token)
    entry = _LOCAL_TOKEN_CACHE.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at <= int(time.time()):
        _LOCAL_TOKEN_CACHE.pop(key, None)
        return None
    return payload


def _local_cache_set(token: str, payload: Dict[str, Any], ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    expires_at = int(time.time()) + ttl_seconds
    key = _token_hash(token)
    _LOCAL_TOKEN_CACHE[key] = (expires_at, payload)
    if len(_LOCAL_TOKEN_CACHE) > INKPASS_LOCAL_TOKEN_CACHE_MAX:
        _prune_local_cache()


def _prune_local_cache() -> None:
    now = int(time.time())
    expired_keys = [key for key, (expires_at, _) in _LOCAL_TOKEN_CACHE.items() if expires_at <= now]
    for key in expired_keys:
        _LOCAL_TOKEN_CACHE.pop(key, None)
    while len(_LOCAL_TOKEN_CACHE) > INKPASS_LOCAL_TOKEN_CACHE_MAX:
        _LOCAL_TOKEN_CACHE.pop(next(iter(_LOCAL_TOKEN_CACHE)), None)


async def validate_token(token: str) -> Optional[UserResponse]:
    """
    Validate a JWT token with inkPass.

    Args:
        token: JWT access token

    Returns:
        UserResponse if valid, None if invalid

    Raises:
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        local_key = _inkpass_verify_key()
        if local_key:
            claims = _decode_token_local(token)
            if not claims:
                return None
            if await _is_token_revoked(token):
                return None
            user = _claims_to_user_response(claims)
            if user:
                logger.debug("Token validated locally", user_id=user.id, email=user.email)
                return user
            return None

        cached_local = _local_cache_get(token)
        if cached_local:
            user = UserResponse(**cached_local)
            logger.debug("Token validated from local cache", user_id=user.id, email=user.email)
            return user

        cache_key = _token_cache_key(token)
        cached = await _cache_get(cache_key)
        if cached:
            try:
                user_payload = json.loads(cached)
                user = UserResponse(**user_payload)
            except Exception as e:
                logger.warning("Token cache parse failed", error=str(e))
            else:
                logger.debug("Token validated from cache", user_id=user.id, email=user.email)
                token_ttl = _token_ttl_seconds(token)
                ttl_seconds = _cap_ttl(INKPASS_TOKEN_CACHE_TTL_SECONDS, token_ttl)
                _local_cache_set(token, user_payload, ttl_seconds)
                return user

        user = await inkpass_client.validate_token(token)
        if user:
            logger.debug("Token validated", user_id=user.id, email=user.email)
            token_ttl = _token_ttl_seconds(token)
            ttl_seconds = _cap_ttl(INKPASS_TOKEN_CACHE_TTL_SECONDS, token_ttl)
            await _cache_set(cache_key, json.dumps(user.model_dump()), ttl_seconds)
            _local_cache_set(token, user.model_dump(), ttl_seconds)
        else:
            logger.debug("Token validation failed")
        return user
    except ServiceUnavailableError as e:
        logger.error("inkPass service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Token validation error", error=str(e))
        return None


INKPASS_API_KEY_CACHE_TTL_SECONDS = int(os.getenv("INKPASS_API_KEY_CACHE_TTL_SECONDS", "300"))


def _api_key_cache_key(api_key: str) -> str:
    return f"inkpass:apikey:{_token_hash(api_key)}"


async def validate_api_key(api_key: str) -> Optional[APIKeyInfoResponse]:
    """
    Validate an API key with inkPass.

    Args:
        api_key: The API key (e.g. ``inkpass_...``)

    Returns:
        APIKeyInfoResponse if valid, None if invalid

    Raises:
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        cache_key = _api_key_cache_key(api_key)
        cached = await _cache_get(cache_key)
        if cached is not None:
            try:
                return APIKeyInfoResponse(**json.loads(cached))
            except Exception as e:
                logger.warning("API key cache parse failed", error=str(e))

        result = await inkpass_client.validate_api_key(api_key)
        if result:
            logger.debug("API key validated", key_id=result.id)
            await _cache_set(
                cache_key,
                json.dumps(result.model_dump()),
                INKPASS_API_KEY_CACHE_TTL_SECONDS,
            )
        else:
            logger.debug("API key validation failed")
        return result
    except ServiceUnavailableError:
        raise
    except Exception as e:
        logger.warning("API key validation error", error=str(e))
        return None


async def check_permission(
    token: str,
    resource: str,
    action: str,
    context: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Check if user has permission for a specific resource and action.

    This is fail-safe: returns False on errors to deny access by default.
    Rate limit errors are re-raised as HTTP 429 to inform the client.

    Args:
        token: JWT access token
        resource: Resource name (e.g., "workflows", "agents")
        action: Action name (e.g., "read", "write", "execute")
        context: Optional ABAC context

    Returns:
        True if user has permission, False otherwise

    Raises:
        HTTPException: 429 if rate limited by inkPass
    """
    try:
        if await _is_token_revoked(token):
            return False

        cache_key = _permission_cache_key(token, resource, action, context)
        cached = await _cache_get(cache_key)
        if cached is not None:
            return cached == "1"

        has_permission = await inkpass_client.check_permission(
            token=token,
            resource=resource,
            action=action,
            context=context
        )

        logger.debug(
            "Permission check",
            resource=resource,
            action=action,
            has_permission=has_permission
        )

        token_ttl = _token_ttl_seconds(token)
        ttl_seconds = _cap_ttl(INKPASS_PERMISSION_CACHE_TTL_SECONDS, token_ttl)
        await _cache_set(cache_key, "1" if has_permission else "0", ttl_seconds)

        return has_permission

    except RateLimitError as e:
        # Re-raise rate limit errors as HTTP 429 so clients know to back off
        logger.error(
            "Permission check failed",
            resource=resource,
            action=action,
            response=str(e),
            status_code=429
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": "60"}
        )

    except Exception as e:
        logger.warning(
            "Permission check failed",
            resource=resource,
            action=action,
            error=str(e)
        )
        # Fail-safe: deny access on errors
        return False


async def login(email: str, password: str) -> Optional[TokenResponse]:
    """
    Authenticate user with inkPass.

    Args:
        email: User email
        password: User password

    Returns:
        TokenResponse if successful, None otherwise

    Raises:
        AuthenticationError: If credentials are invalid
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        tokens = await inkpass_client.login(email, password)
        logger.info("User logged in", email=email)
        return tokens
    except AuthenticationError as e:
        logger.warning("Login failed", email=email, error=str(e))
        raise
    except ServiceUnavailableError as e:
        logger.error("inkPass service unavailable during login", error=str(e))
        raise


async def register_user(
    email: str,
    password: str,
    organization_name: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register a new user with inkPass.

    Args:
        email: User email
        password: User password
        organization_name: Optional organization name
        first_name: User first name
        last_name: User last name

    Returns:
        Registration response with user_id and organization_id

    Raises:
        ValidationError: If input is invalid
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        registration = await inkpass_client.register(
            email=email,
            password=password,
            organization_name=organization_name,
            first_name=first_name,
            last_name=last_name,
        )

        logger.info(
            "User registered",
            email=email,
            user_id=registration.user_id,
            organization_id=registration.organization_id
        )

        return {
            "user_id": registration.user_id,
            "email": registration.email,
            "organization_id": registration.organization_id
        }

    except InkPassError as e:
        logger.error("User registration failed", email=email, error=str(e))
        raise


async def create_api_key(
    token: str,
    name: str,
    scopes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create an API key in inkPass.

    Args:
        token: JWT access token
        name: API key name
        scopes: Optional list of scopes

    Returns:
        API key response with key and metadata

    Raises:
        AuthenticationError: If token is invalid
        PermissionDeniedError: If user lacks permission
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        api_key = await inkpass_client.create_api_key(
            token=token,
            name=name,
            scopes=scopes
        )

        logger.info("API key created", name=name, key_id=api_key.id)

        return {
            "id": api_key.id,
            "key": api_key.key,
            "name": api_key.name,
            "scopes": api_key.scopes,
            "created_at": api_key.created_at
        }

    except (AuthenticationError, PermissionDeniedError) as e:
        logger.warning("API key creation failed", name=name, error=str(e))
        raise
    except InkPassError as e:
        logger.error("API key creation error", name=name, error=str(e))
        raise


async def verify_email(email: str, code: str) -> Dict[str, Any]:
    """
    Verify email address with OTP code.

    Args:
        email: User email
        code: 6-digit verification code

    Returns:
        Response with verification message

    Raises:
        ValidationError: If code is invalid or expired
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        result = await inkpass_client.verify_email(email, code)
        logger.info("Email verified", email=email)
        return result
    except InkPassError as e:
        logger.error("Email verification failed", email=email, error=str(e))
        raise


async def resend_verification(email: str) -> Dict[str, Any]:
    """
    Resend email verification code.

    Args:
        email: User email

    Returns:
        Response with message

    Raises:
        ServiceUnavailableError: If inkPass service is unavailable
    """
    try:
        result = await inkpass_client.resend_verification(email)
        logger.info("Verification code resent", email=email)
        return result
    except InkPassError as e:
        logger.error("Resend verification failed", email=email, error=str(e))
        raise


async def health_check() -> bool:
    """
    Check if inkPass service is healthy.

    Returns:
        True if service is healthy, False otherwise
    """
    try:
        # Try a simple token validation with an invalid token
        # If we get back None (invalid token) without errors, service is healthy
        await inkpass_client.validate_token("health-check-token")
        return True
    except ServiceUnavailableError:
        return False
    except Exception:
        # Other errors (like authentication errors) still mean the service is up
        return True


# Export all public functions
__all__ = [
    "inkpass_client",
    "inkpass_config",
    "validate_token",
    "validate_api_key",
    "check_permission",
    "login",
    "register_user",
    "create_api_key",
    "verify_email",
    "resend_verification",
    "health_check",
]
