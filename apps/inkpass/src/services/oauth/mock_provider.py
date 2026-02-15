"""Mock OAuth Provider for testing"""

import uuid
from typing import Dict, Any
from datetime import datetime, timedelta
from .provider_interface import (
    OAuthProviderInterface,
    OAuthUserInfo,
    OAuthTokens,
    TokenExchangeError,
    UserInfoError,
    TokenRefreshError,
)


class MockOAuthProvider(OAuthProviderInterface):
    """
    Mock OAuth provider for testing.

    This provider simulates OAuth flow without requiring actual OAuth credentials
    or external API calls. Useful for:
    - Unit testing
    - Integration testing
    - Development without real OAuth apps
    - CI/CD pipelines

    Single Responsibility: Simulate OAuth provider behavior for testing.
    """

    # Class-level storage for mock data (in-memory for testing)
    _mock_codes: Dict[str, Dict[str, Any]] = {}  # auth_code -> {user_id, email, name}
    _mock_tokens: Dict[str, Dict[str, Any]] = {}  # access_token -> user_data
    _mock_refresh_tokens: Dict[str, str] = {}  # refresh_token -> access_token

    def __init__(self, provider_name: str = "mock", client_id: str = "mock_client_id",
                 client_secret: str = "mock_secret", redirect_uri: str = "http://localhost:8002/auth/callback",
                 scopes: list[str] = None):
        """Initialize mock provider"""
        scopes = scopes or ["email", "profile"]
        super().__init__(provider_name, client_id, client_secret, redirect_uri, scopes)

    def get_authorization_url(self, state: str) -> str:
        """
        Generate mock authorization URL.

        For testing, you can append ?mock_user_id=X to simulate different users.
        """
        base_url = f"https://mock-oauth-provider.example.com/authorize"
        scope_param = "+".join(self.scopes)
        return (
            f"{base_url}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"response_type=code&"
            f"scope={scope_param}&"
            f"state={state}"
        )

    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens:
        """
        Exchange authorization code for mock tokens.

        For testing, the code should be generated using create_mock_code() method.
        """
        if code not in self._mock_codes:
            raise TokenExchangeError(
                f"Invalid authorization code: {code}",
                provider=self.provider_name,
                details={"code": code}
            )

        user_data = self._mock_codes.pop(code)  # One-time use

        # Generate mock tokens
        access_token = f"mock_access_token_{uuid.uuid4().hex[:16]}"
        refresh_token = f"mock_refresh_token_{uuid.uuid4().hex[:16]}"

        # Store tokens for later validation
        self._mock_tokens[access_token] = {
            **user_data,
            "issued_at": datetime.utcnow().isoformat(),
        }
        self._mock_refresh_tokens[refresh_token] = access_token

        return OAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600,  # 1 hour
            token_type="Bearer"
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """
        Fetch mock user information.
        """
        if access_token not in self._mock_tokens:
            raise UserInfoError(
                f"Invalid or expired access token",
                provider=self.provider_name,
                details={"token_prefix": access_token[:20]}
            )

        user_data = self._mock_tokens[access_token]

        return OAuthUserInfo(
            provider_user_id=user_data["user_id"],
            email=user_data["email"],
            name=user_data.get("name"),
            avatar_url=user_data.get("avatar_url"),
            email_verified=user_data.get("email_verified", True),
            raw_data=user_data
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """
        Refresh mock access token.
        """
        if refresh_token not in self._mock_refresh_tokens:
            raise TokenRefreshError(
                "Invalid refresh token",
                provider=self.provider_name,
                details={"token_prefix": refresh_token[:20]}
            )

        old_access_token = self._mock_refresh_tokens[refresh_token]
        old_user_data = self._mock_tokens.pop(old_access_token, {})

        # Generate new tokens
        new_access_token = f"mock_access_token_{uuid.uuid4().hex[:16]}"
        new_refresh_token = f"mock_refresh_token_{uuid.uuid4().hex[:16]}"

        # Update storage
        self._mock_tokens[new_access_token] = {
            **old_user_data,
            "issued_at": datetime.utcnow().isoformat(),
        }
        del self._mock_refresh_tokens[refresh_token]
        self._mock_refresh_tokens[new_refresh_token] = new_access_token

        return OAuthTokens(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=3600,
            token_type="Bearer"
        )

    # Test helper methods

    @classmethod
    def create_mock_code(cls, user_id: str, email: str, name: str = None,
                         avatar_url: str = None, email_verified: bool = True) -> str:
        """
        Create a mock authorization code for testing.

        This simulates the OAuth provider redirecting back with a code.

        Args:
            user_id: Mock user ID from OAuth provider
            email: User's email
            name: User's full name (optional)
            avatar_url: User's avatar URL (optional)
            email_verified: Whether email is verified

        Returns:
            Authorization code to use in exchange_code_for_tokens()
        """
        code = f"mock_auth_code_{uuid.uuid4().hex[:16]}"
        cls._mock_codes[code] = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "avatar_url": avatar_url,
            "email_verified": email_verified,
        }
        return code

    @classmethod
    def clear_mock_data(cls):
        """Clear all mock data (useful between tests)"""
        cls._mock_codes.clear()
        cls._mock_tokens.clear()
        cls._mock_refresh_tokens.clear()
