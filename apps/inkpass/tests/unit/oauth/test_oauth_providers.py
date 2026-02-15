"""Unit tests for OAuth providers"""

import pytest
from src.services.oauth.mock_provider import MockOAuthProvider
from src.services.oauth.google_provider import GoogleOAuthProvider
from src.services.oauth.provider_factory import OAuthProviderFactory, register_default_providers
from src.services.oauth.provider_interface import (
    OAuthProviderInterface,
    TokenExchangeError,
    UserInfoError,
    TokenRefreshError,
)


class TestMockOAuthProvider:
    """Tests for MockOAuthProvider"""

    def setup_method(self):
        """Clear mock data before each test"""
        MockOAuthProvider.clear_mock_data()

    def test_get_authorization_url(self):
        """Test generating authorization URL"""
        provider = MockOAuthProvider()
        state = "test_state_123"
        url = provider.get_authorization_url(state)

        assert "mock-oauth-provider.example.com/authorize" in url
        assert f"state={state}" in url
        assert "client_id=mock_client_id" in url
        assert "redirect_uri=" in url
        assert "scope=" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens(self):
        """Test exchanging authorization code for tokens"""
        provider = MockOAuthProvider()

        # Create a mock authorization code
        code = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="test@example.com",
            name="Test User"
        )

        # Exchange code for tokens
        tokens = await provider.exchange_code_for_tokens(code)

        assert tokens.access_token.startswith("mock_access_token_")
        assert tokens.refresh_token.startswith("mock_refresh_token_")
        assert tokens.expires_in == 3600
        assert tokens.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_exchange_invalid_code(self):
        """Test exchanging invalid authorization code"""
        provider = MockOAuthProvider()

        with pytest.raises(TokenExchangeError) as exc_info:
            await provider.exchange_code_for_tokens("invalid_code")

        assert "Invalid authorization code" in str(exc_info.value)
        assert exc_info.value.provider == "mock"

    @pytest.mark.asyncio
    async def test_get_user_info(self):
        """Test fetching user information"""
        provider = MockOAuthProvider()

        # Create mock code and exchange for tokens
        code = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="test@example.com",
            name="Test User",
            avatar_url="https://example.com/avatar.jpg",
            email_verified=True
        )
        tokens = await provider.exchange_code_for_tokens(code)

        # Get user info
        user_info = await provider.get_user_info(tokens.access_token)

        assert user_info.provider_user_id == "google_123456"
        assert user_info.email == "test@example.com"
        assert user_info.name == "Test User"
        assert user_info.avatar_url == "https://example.com/avatar.jpg"
        assert user_info.email_verified is True

    @pytest.mark.asyncio
    async def test_get_user_info_invalid_token(self):
        """Test fetching user info with invalid token"""
        provider = MockOAuthProvider()

        with pytest.raises(UserInfoError) as exc_info:
            await provider.get_user_info("invalid_token")

        assert "Invalid or expired access token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_access_token(self):
        """Test refreshing access token"""
        provider = MockOAuthProvider()

        # Create mock code and exchange for tokens
        code = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="test@example.com"
        )
        initial_tokens = await provider.exchange_code_for_tokens(code)

        # Refresh the token
        new_tokens = await provider.refresh_access_token(initial_tokens.refresh_token)

        assert new_tokens.access_token.startswith("mock_access_token_")
        assert new_tokens.refresh_token.startswith("mock_refresh_token_")
        assert new_tokens.access_token != initial_tokens.access_token
        assert new_tokens.refresh_token != initial_tokens.refresh_token

        # Old token should no longer work
        with pytest.raises(UserInfoError):
            await provider.get_user_info(initial_tokens.access_token)

        # New token should work
        user_info = await provider.get_user_info(new_tokens.access_token)
        assert user_info.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """Test refreshing with invalid refresh token"""
        provider = MockOAuthProvider()

        with pytest.raises(TokenRefreshError) as exc_info:
            await provider.refresh_access_token("invalid_refresh_token")

        assert "Invalid refresh token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_token(self):
        """Test token validation"""
        provider = MockOAuthProvider()

        # Create mock code and get tokens
        code = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="test@example.com"
        )
        tokens = await provider.exchange_code_for_tokens(code)

        # Valid token should return True
        is_valid = await provider.validate_token(tokens.access_token)
        assert is_valid is True

        # Invalid token should return False
        is_valid = await provider.validate_token("invalid_token")
        assert is_valid is False


class TestGoogleOAuthProvider:
    """Tests for GoogleOAuthProvider"""

    def test_get_authorization_url(self):
        """Test generating Google authorization URL"""
        provider = GoogleOAuthProvider(
            client_id="test_client_id",
            client_secret="test_secret",
            redirect_uri="http://localhost:8002/callback"
        )
        state = "test_state_123"
        url = provider.get_authorization_url(state)

        assert "accounts.google.com/o/oauth2/v2/auth" in url
        assert f"state={state}" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "access_type=offline" in url  # Should request refresh token
        assert "prompt=consent" in url

    def test_provider_urls(self):
        """Test that Google provider has correct URLs"""
        provider = GoogleOAuthProvider(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost"
        )

        assert provider.AUTHORIZATION_URL == "https://accounts.google.com/o/oauth2/v2/auth"
        assert provider.TOKEN_URL == "https://oauth2.googleapis.com/token"
        assert provider.USER_INFO_URL == "https://www.googleapis.com/oauth2/v2/userinfo"

    def test_default_scopes(self):
        """Test that Google provider has correct default scopes"""
        provider = GoogleOAuthProvider(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost"
        )

        assert "openid" in provider.scopes
        assert "https://www.googleapis.com/auth/userinfo.email" in provider.scopes
        assert "https://www.googleapis.com/auth/userinfo.profile" in provider.scopes


class TestOAuthProviderFactory:
    """Tests for OAuthProviderFactory"""

    def setup_method(self):
        """Clear factory registry before each test"""
        OAuthProviderFactory.clear_registry()

    def test_register_provider(self):
        """Test registering a provider"""
        OAuthProviderFactory.register("mock", MockOAuthProvider)

        assert OAuthProviderFactory.is_registered("mock")
        assert "mock" in OAuthProviderFactory.list_providers()

    def test_register_duplicate_provider(self):
        """Test that registering duplicate provider raises error"""
        OAuthProviderFactory.register("mock", MockOAuthProvider)

        with pytest.raises(ValueError) as exc_info:
            OAuthProviderFactory.register("mock", MockOAuthProvider)

        assert "already registered" in str(exc_info.value)

    def test_register_invalid_provider(self):
        """Test that registering invalid class raises error"""
        class InvalidProvider:
            pass

        with pytest.raises(ValueError) as exc_info:
            OAuthProviderFactory.register("invalid", InvalidProvider)

        assert "must implement OAuthProviderInterface" in str(exc_info.value)

    def test_create_provider(self):
        """Test creating a provider instance"""
        OAuthProviderFactory.register("mock", MockOAuthProvider)

        provider = OAuthProviderFactory.create(
            "mock",
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost"
        )

        assert isinstance(provider, MockOAuthProvider)
        assert provider.client_id == "test_id"
        assert provider.client_secret == "test_secret"

    def test_create_unregistered_provider(self):
        """Test creating unregistered provider raises error"""
        with pytest.raises(ValueError) as exc_info:
            OAuthProviderFactory.create("unregistered")

        assert "not found" in str(exc_info.value)
        assert "Available providers:" in str(exc_info.value)

    def test_unregister_provider(self):
        """Test unregistering a provider"""
        OAuthProviderFactory.register("mock", MockOAuthProvider)
        assert OAuthProviderFactory.is_registered("mock")

        OAuthProviderFactory.unregister("mock")
        assert not OAuthProviderFactory.is_registered("mock")

    def test_list_providers(self):
        """Test listing all providers"""
        OAuthProviderFactory.register("mock", MockOAuthProvider)
        OAuthProviderFactory.register("google", GoogleOAuthProvider)

        providers = OAuthProviderFactory.list_providers()
        assert "mock" in providers
        assert "google" in providers
        assert len(providers) == 2

    def test_register_default_providers(self):
        """Test registering default providers"""
        register_default_providers()

        assert OAuthProviderFactory.is_registered("mock")
        assert OAuthProviderFactory.is_registered("google")
