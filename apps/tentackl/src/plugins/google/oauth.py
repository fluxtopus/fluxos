"""Google OAuth plugin handlers."""

import os
from typing import Any, Dict
from urllib.parse import urlencode
import base64
import hashlib
import hmac
import json
import secrets
import time

import httpx
import structlog

from .constants import (
    GOOGLE_AUTH_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO_URL,
    CALENDAR_ASSISTANT_SCOPES,
)
from .exceptions import GooglePluginError, GoogleOAuthError
from .token_store import get_token_store

logger = structlog.get_logger()
STATE_TTL_SECONDS = int(os.getenv("GOOGLE_OAUTH_STATE_TTL_SECONDS", "600"))


def _get_google_credentials() -> Dict[str, str]:
    """Get Google OAuth credentials from environment."""
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/v1/oauth/google/callback"
    )

    if not client_id or not client_secret:
        raise GoogleOAuthError(
            "Google OAuth credentials not configured. "
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


async def google_oauth_start_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Google OAuth authorization URL.

    Inputs:
        user_id: User ID to associate with OAuth tokens
        scopes: Optional list of additional scopes

    Returns:
        Dictionary with authorization URL
    """
    user_id = inputs.get("user_id")
    if not user_id:
        raise GooglePluginError("'user_id' is required")

    try:
        creds = _get_google_credentials()
        scopes = inputs.get("scopes", CALENDAR_ASSISTANT_SCOPES)
        store = get_token_store()

        nonce = secrets.token_urlsafe(24)
        issued_at = int(time.time())
        state_payload = {
            "uid": user_id,
            "nonce": nonce,
            "iat": issued_at,
        }
        payload_json = json.dumps(state_payload, separators=(",", ":")).encode()
        payload_b64 = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
        state_secret = os.getenv("GOOGLE_OAUTH_STATE_SECRET") or os.getenv("TENTACKL_SECRET_KEY")
        if not state_secret:
            raise GoogleOAuthError("GOOGLE_OAUTH_STATE_SECRET (or TENTACKL_SECRET_KEY) must be configured")
        signature = hmac.new(
            state_secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()
        state_token = f"{payload_b64}.{signature}"
        await store.store_oauth_state_nonce(nonce=nonce, user_id=user_id, ttl_seconds=STATE_TTL_SECONDS)

        # Build authorization URL
        params = {
            "client_id": creds["client_id"],
            "redirect_uri": creds["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state_token,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }

        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

        logger.info("Generated Google OAuth URL", user_id=user_id)

        return {
            "success": True,
            "authorization_url": auth_url,
            "user_id": user_id,
            "scopes": scopes
        }

    except Exception as e:
        logger.error("Failed to generate OAuth URL", error=str(e))
        raise GooglePluginError(f"Failed to generate OAuth URL: {str(e)}")


async def google_oauth_callback_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exchange authorization code for tokens.

    Inputs:
        code: Authorization code from Google
        state: State token (contains user_id)

    Returns:
        Dictionary with success status and user email
    """
    code = inputs.get("code")
    state = inputs.get("state")

    if not code:
        raise GooglePluginError("'code' is required")
    if not state:
        raise GooglePluginError("'state' is required")
    state_secret = os.getenv("GOOGLE_OAUTH_STATE_SECRET") or os.getenv("TENTACKL_SECRET_KEY")
    if not state_secret:
        raise GoogleOAuthError("GOOGLE_OAUTH_STATE_SECRET (or TENTACKL_SECRET_KEY) must be configured")

    try:
        payload_b64, signature = state.rsplit(".", 1)
    except ValueError as exc:
        raise GoogleOAuthError("Invalid OAuth state token") from exc

    expected_signature = hmac.new(
        state_secret.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise GoogleOAuthError("Invalid OAuth state signature")

    padded_payload = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        decoded_payload = base64.urlsafe_b64decode(padded_payload.encode()).decode()
        state_payload = json.loads(decoded_payload)
    except Exception as exc:
        raise GoogleOAuthError("Invalid OAuth state payload") from exc

    user_id = state_payload.get("uid")
    nonce = state_payload.get("nonce")
    issued_at = state_payload.get("iat")
    if not user_id or not nonce or not issued_at:
        raise GoogleOAuthError("Invalid OAuth state payload")

    if int(time.time()) - int(issued_at) > STATE_TTL_SECONDS:
        raise GoogleOAuthError("OAuth state token expired")

    store = get_token_store()
    nonce_valid = await store.consume_oauth_state_nonce(nonce=nonce, user_id=user_id)
    if not nonce_valid:
        raise GoogleOAuthError("OAuth state token is invalid or already used")

    try:
        creds = _get_google_credentials()

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                    "redirect_uri": creds["redirect_uri"],
                    "grant_type": "authorization_code"
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                raise GoogleOAuthError(
                    f"Token exchange failed: {error_data.get('error_description', error_data)}"
                )

            token_data = response.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not refresh_token:
            logger.warning(
                "No refresh token received. User may need to revoke and re-authorize.",
                user_id=user_id
            )

        # Get user info
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = response.json()

        # Store tokens
        store = get_token_store()
        await store.store_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_in=expires_in
        )

        logger.info(
            "Google OAuth completed",
            user_id=user_id,
            email=user_info.get("email")
        )

        return {
            "success": True,
            "user_id": user_id,
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture")
        }

    except GoogleOAuthError:
        raise
    except Exception as e:
        logger.error("OAuth callback failed", error=str(e))
        raise GooglePluginError(f"OAuth callback failed: {str(e)}")


async def get_valid_access_token(user_id: str) -> str:
    """
    Get a valid access token, refreshing if needed.

    Args:
        user_id: User ID

    Returns:
        Valid access token

    Raises:
        GoogleOAuthError: If no tokens or refresh fails
    """
    store = get_token_store()
    tokens = await store.get_tokens(user_id)

    if not tokens:
        raise GoogleOAuthError(
            f"No Google OAuth tokens for user {user_id}. "
            "User needs to connect their Google account first."
        )

    # Check if token needs refresh
    if await store.is_token_expired(user_id):
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise GoogleOAuthError(
                "Access token expired and no refresh token available. "
                "User needs to re-authorize."
            )

        # Refresh the token
        creds = _get_google_credentials()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                raise GoogleOAuthError(
                    f"Token refresh failed: {error_data.get('error_description', error_data)}"
                )

            token_data = response.json()

        # Update stored tokens
        await store.store_tokens(
            user_id=user_id,
            access_token=token_data["access_token"],
            refresh_token=refresh_token,  # Keep existing refresh token
            expires_in=token_data.get("expires_in", 3600)
        )

        logger.info("Refreshed Google OAuth token", user_id=user_id)
        return token_data["access_token"]

    return tokens["access_token"]


async def google_oauth_status_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check Google OAuth connection status for a user.

    Inputs:
        user_id: User ID

    Returns:
        Dictionary with connection status
    """
    user_id = inputs.get("user_id")
    if not user_id:
        raise GooglePluginError("'user_id' is required")

    try:
        store = get_token_store()
        tokens = await store.get_tokens(user_id)

        if not tokens:
            return {
                "connected": False,
                "user_id": user_id,
                "message": "Google account not connected"
            }

        is_expired = await store.is_token_expired(user_id)
        has_refresh_token = bool(tokens.get("refresh_token"))

        return {
            "connected": True,
            "user_id": user_id,
            "token_expired": is_expired,
            "has_refresh_token": has_refresh_token,
            "expires_at": tokens.get("expires_at"),
            "updated_at": tokens.get("updated_at")
        }

    except Exception as e:
        logger.error("Failed to check OAuth status", error=str(e))
        return {
            "connected": False,
            "user_id": user_id,
            "error": str(e)
        }


# Plugin definitions for OAuth handlers
OAUTH_PLUGIN_DEFINITIONS = [
    {
        "name": "google_oauth_start",
        "description": "Generate Google OAuth authorization URL",
        "handler": google_oauth_start_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["user_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "authorization_url": {"type": "string"},
                "user_id": {"type": "string"}
            }
        },
        "category": "google",
    },
    {
        "name": "google_oauth_callback",
        "description": "Exchange Google OAuth authorization code for tokens",
        "handler": google_oauth_callback_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "state": {"type": "string"}
            },
            "required": ["code", "state"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "user_id": {"type": "string"},
                "email": {"type": "string"}
            }
        },
        "category": "google",
    },
    {
        "name": "google_oauth_status",
        "description": "Check Google OAuth connection status",
        "handler": google_oauth_status_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"}
            },
            "required": ["user_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "connected": {"type": "boolean"},
                "user_id": {"type": "string"}
            }
        },
        "category": "google",
    },
]
