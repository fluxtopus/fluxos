"""Twitter/X OAuth 2.0 provider implementation."""

from __future__ import annotations

from urllib.parse import urlencode
import logging

import httpx

from src.core.config import settings
from src.infrastructure.integrations.oauth_provider_base import (
    IntegrationOAuthProvider,
    OAuthTokenResult,
)

logger = logging.getLogger(__name__)

TWITTER_AUTH_URL = "https://x.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.x.com/2/oauth2/token"
TWITTER_REVOKE_URL = "https://api.x.com/2/oauth2/revoke"
TWITTER_SCOPES = "tweet.read tweet.write users.read offline.access"


class TwitterOAuthProvider(IntegrationOAuthProvider):
    """OAuth 2.0 provider for Twitter/X with PKCE."""

    provider_name = "twitter"

    def __init__(self) -> None:
        self.client_id = settings.X_OAUTH2_CLIENT_ID or ""
        self.client_secret = settings.X_OAUTH2_CLIENT_SECRET or ""

    def get_authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": TWITTER_SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{TWITTER_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OAuthTokenResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TWITTER_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                    "client_id": self.client_id,
                },
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        logger.info("Twitter OAuth code exchange successful")
        return OAuthTokenResult(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            token_type=data.get("token_type", "bearer"),
        )

    async def refresh_token(self, refresh_token: str) -> OAuthTokenResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TWITTER_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                },
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        logger.info("Twitter OAuth token refresh successful")
        return OAuthTokenResult(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            token_type=data.get("token_type", "bearer"),
        )

    async def revoke_token(self, access_token: str) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    TWITTER_REVOKE_URL,
                    data={
                        "token": access_token,
                        "token_type_hint": "access_token",
                        "client_id": self.client_id,
                    },
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
            logger.info("Twitter OAuth token revoked")
            return True
        except Exception as exc:
            logger.error("Failed to revoke Twitter token: %s", exc)
            return False
