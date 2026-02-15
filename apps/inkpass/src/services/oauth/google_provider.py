"""Google OAuth Provider"""

import httpx
from typing import Optional
from urllib.parse import urlencode
from .provider_interface import (
    OAuthProviderInterface,
    OAuthUserInfo,
    OAuthTokens,
    TokenExchangeError,
    UserInfoError,
    TokenRefreshError,
)


class GoogleOAuthProvider(OAuthProviderInterface):
    """
    Google OAuth 2.0 provider implementation.

    Implements OAuth 2.0 flow with Google's authentication service.
    Supports authorization code flow, token refresh, and user info retrieval.

    Single Responsibility: Handle OAuth communication with Google only.

    References:
    - https://developers.google.com/identity/protocols/oauth2
    - https://developers.google.com/identity/protocols/oauth2/web-server
    """

    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    # Default scopes for basic profile and email
    DEFAULT_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str,
                 scopes: Optional[list[str]] = None):
        """
        Initialize Google OAuth provider.

        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: Callback URL for OAuth flow
            scopes: List of OAuth scopes (defaults to email + profile)
        """
        scopes = scopes or self.DEFAULT_SCOPES
        super().__init__(
            provider_name="google",
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes
        )

    def get_authorization_url(self, state: str) -> str:
        """
        Generate Google authorization URL.

        Args:
            state: CSRF protection token

        Returns:
            Full authorization URL with query parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
        }
        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens:
        """
        Exchange authorization code for Google access tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            OAuth tokens including access and refresh tokens

        Raises:
            TokenExchangeError: If token exchange fails
        """
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.TOKEN_URL, data=data)
                response.raise_for_status()
                token_data = response.json()

            return OAuthTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
                token_type=token_data.get("token_type", "Bearer"),
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json() if e.response.text else {}
            raise TokenExchangeError(
                f"Failed to exchange code for tokens: {e.response.status_code}",
                provider=self.provider_name,
                details={
                    "status_code": e.response.status_code,
                    "error": error_detail.get("error"),
                    "error_description": error_detail.get("error_description"),
                }
            )
        except Exception as e:
            raise TokenExchangeError(
                f"Unexpected error during token exchange: {str(e)}",
                provider=self.provider_name,
                details={"error": str(e)}
            )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """
        Fetch user information from Google.

        Args:
            access_token: Valid Google OAuth access token

        Returns:
            Standardized user information

        Raises:
            UserInfoError: If user info fetch fails
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.USER_INFO_URL, headers=headers)
                response.raise_for_status()
                user_data = response.json()

            return OAuthUserInfo(
                provider_user_id=user_data["id"],
                email=user_data["email"],
                name=user_data.get("name"),
                avatar_url=user_data.get("picture"),
                email_verified=user_data.get("verified_email", False),
                raw_data=user_data,
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json() if e.response.text else {}
            raise UserInfoError(
                f"Failed to fetch user info: {e.response.status_code}",
                provider=self.provider_name,
                details={
                    "status_code": e.response.status_code,
                    "error": error_detail.get("error"),
                    "error_description": error_detail.get("error_description"),
                }
            )
        except Exception as e:
            raise UserInfoError(
                f"Unexpected error fetching user info: {str(e)}",
                provider=self.provider_name,
                details={"error": str(e)}
            )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """
        Refresh Google access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New OAuth tokens

        Raises:
            TokenRefreshError: If token refresh fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.TOKEN_URL, data=data)
                response.raise_for_status()
                token_data = response.json()

            return OAuthTokens(
                access_token=token_data["access_token"],
                refresh_token=refresh_token,  # Google doesn't return new refresh token
                expires_in=token_data.get("expires_in"),
                token_type=token_data.get("token_type", "Bearer"),
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json() if e.response.text else {}
            raise TokenRefreshError(
                f"Failed to refresh token: {e.response.status_code}",
                provider=self.provider_name,
                details={
                    "status_code": e.response.status_code,
                    "error": error_detail.get("error"),
                    "error_description": error_detail.get("error_description"),
                }
            )
        except Exception as e:
            raise TokenRefreshError(
                f"Unexpected error refreshing token: {str(e)}",
                provider=self.provider_name,
                details={"error": str(e)}
            )

    async def validate_token(self, access_token: str) -> bool:
        """
        Validate Google access token using tokeninfo endpoint.

        Args:
            access_token: Token to validate

        Returns:
            True if token is valid, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.TOKEN_INFO_URL}?access_token={access_token}"
                )
                if response.status_code == 200:
                    token_info = response.json()
                    # Verify the token is for our app
                    return token_info.get("aud") == self.client_id
                return False
        except Exception:
            return False
