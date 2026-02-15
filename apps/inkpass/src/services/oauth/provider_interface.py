"""OAuth Provider Interface - Strategy Pattern for OAuth providers"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class OAuthUserInfo:
    """Standardized user information from OAuth providers"""
    provider_user_id: str  # Unique ID from OAuth provider
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    email_verified: bool = False
    raw_data: Optional[Dict[str, Any]] = None  # Full profile data from provider


@dataclass
class OAuthTokens:
    """OAuth tokens from provider"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # Seconds until expiration
    token_type: str = "Bearer"


class OAuthProviderInterface(ABC):
    """
    Abstract base class for OAuth providers.

    This interface defines the contract that all OAuth providers must implement.
    Each provider (Google, Apple, GitHub, etc.) implements this interface using
    the Strategy Pattern, allowing easy addition of new providers without
    modifying existing code.

    Single Responsibility: Each provider handles ONLY OAuth communication with
    one specific OAuth service.
    """

    def __init__(self, provider_name: str, client_id: str, client_secret: str,
                 redirect_uri: str, scopes: list[str]):
        """
        Initialize OAuth provider.

        Args:
            provider_name: Name of the provider (e.g., "google", "apple")
            client_id: OAuth client ID
            client_secret: OAuth client secret
            redirect_uri: Callback URL for OAuth flow
            scopes: List of OAuth scopes to request
        """
        self.provider_name = provider_name
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """
        Generate the authorization URL for OAuth flow.

        Args:
            state: CSRF protection token

        Returns:
            Authorization URL to redirect user to
        """
        pass

    @abstractmethod
    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens:
        """
        Exchange authorization code for access tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            OAuth tokens (access_token, refresh_token, etc.)

        Raises:
            OAuthError: If token exchange fails
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """
        Fetch user information from OAuth provider.

        Args:
            access_token: Valid OAuth access token

        Returns:
            Standardized user information

        Raises:
            OAuthError: If user info fetch fails
        """
        pass

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New OAuth tokens

        Raises:
            OAuthError: If token refresh fails
        """
        pass

    async def validate_token(self, access_token: str) -> bool:
        """
        Validate an access token (optional, provider-specific).

        Args:
            access_token: Token to validate

        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Default implementation: try to fetch user info
            await self.get_user_info(access_token)
            return True
        except Exception:
            return False


class OAuthError(Exception):
    """Base exception for OAuth-related errors"""

    def __init__(self, message: str, provider: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.provider = provider
        self.details = details or {}


class TokenExchangeError(OAuthError):
    """Error during token exchange"""
    pass


class UserInfoError(OAuthError):
    """Error fetching user info"""
    pass


class TokenRefreshError(OAuthError):
    """Error refreshing token"""
    pass
