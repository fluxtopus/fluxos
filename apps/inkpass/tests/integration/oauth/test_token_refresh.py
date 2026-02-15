"""Integration tests for OAuth token refresh functionality"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.database.models import OAuthProvider, OAuthAccount, User, Organization
from src.services.oauth_service import OAuthService
from src.services.oauth.mock_provider import MockOAuthProvider
from src.services.oauth.provider_factory import OAuthProviderFactory
from src.security.password import hash_password


@pytest.fixture(scope="function", autouse=True)
def setup_oauth_factory():
    """Register OAuth providers before each test"""
    OAuthProviderFactory.clear_registry()
    OAuthProviderFactory.register("mock", MockOAuthProvider)
    yield
    OAuthProviderFactory.clear_registry()


@pytest.fixture(scope="function")
def oauth_provider(db: Session):
    """Create a mock OAuth provider in database"""
    provider = OAuthProvider(
        provider_name="mock",
        client_id="test_client_id",
        client_secret="test_secret",
        authorization_url="https://mock-oauth.example.com/authorize",
        token_url="https://mock-oauth.example.com/token",
        user_info_url="https://mock-oauth.example.com/userinfo",
        scopes=["email", "profile"],
        is_active=True
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)

    # Clear any previous mock data
    MockOAuthProvider.clear_mock_data()

    return provider


@pytest.fixture(scope="function")
def user_with_oauth(db: Session, oauth_provider: OAuthProvider):
    """Create a user with OAuth account for testing"""
    # Create organization
    org = Organization(name="Test Org", slug="test-org")
    db.add(org)
    db.flush()

    # Create user
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("password"),
        organization_id=org.id
    )
    db.add(user)
    db.flush()

    # Create mock OAuth flow to get valid tokens
    code = MockOAuthProvider.create_mock_code(
        user_id="test_user_123",
        email="testuser@example.com",
        name="Test User"
    )

    # Run the OAuth flow to create account with encrypted tokens
    service = OAuthService(db)
    import asyncio
    loop = asyncio.get_event_loop()
    _, _ = loop.run_until_complete(service.complete_oauth_flow(
        provider_name="mock",
        code=code,
        redirect_uri="http://localhost:8002/callback"
    ))

    # Get the OAuth account
    oauth_account = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id
    ).first()

    return user, oauth_account


@pytest.mark.integration
class TestTokenRefresh:
    """Integration tests for OAuth token refresh"""

    def test_is_token_expired_not_expired(self, db: Session, user_with_oauth):
        """Test checking if token is expired when it's not"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Token expires in 1 hour (from OAuth flow)
        assert oauth_account.token_expires_at > datetime.utcnow()

        # Should not be considered expired
        is_expired = service.is_token_expired(oauth_account)
        assert is_expired is False

    def test_is_token_expired_with_buffer(self, db: Session, user_with_oauth):
        """Test checking if token is expired within buffer time"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Set token to expire in 4 minutes
        oauth_account.token_expires_at = datetime.utcnow() + timedelta(minutes=4)
        db.commit()

        # With default buffer (5 minutes), should be considered expired
        is_expired = service.is_token_expired(oauth_account)
        assert is_expired is True

        # With custom buffer (3 minutes), should not be considered expired
        is_expired = service.is_token_expired(oauth_account, buffer_seconds=180)
        assert is_expired is False

    def test_is_token_expired_already_expired(self, db: Session, user_with_oauth):
        """Test checking if token is expired when it already expired"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Set token to expire 1 hour ago
        oauth_account.token_expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        # Should be considered expired
        is_expired = service.is_token_expired(oauth_account)
        assert is_expired is True

    def test_is_token_expired_no_expiration(self, db: Session, user_with_oauth):
        """Test checking if token is expired when no expiration is set"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Clear expiration time
        oauth_account.token_expires_at = None
        db.commit()

        # Should not be considered expired (tokens without expiration never expire)
        is_expired = service.is_token_expired(oauth_account)
        assert is_expired is False

    @pytest.mark.asyncio
    async def test_refresh_oauth_token(self, db: Session, user_with_oauth):
        """Test refreshing an OAuth token"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Get original tokens
        original_access, original_refresh = service.get_decrypted_tokens(oauth_account)

        # Refresh the token
        updated_account = await service.refresh_oauth_token(oauth_account.id)

        # Get new tokens
        new_access, new_refresh = service.get_decrypted_tokens(updated_account)

        # Tokens should be different (MockProvider generates new random tokens)
        assert new_access != original_access
        assert new_refresh != original_refresh

        # New tokens should follow expected pattern
        assert new_access.startswith("mock_access_token_")
        assert new_refresh.startswith("mock_refresh_token_")

        # Token expiration should be updated
        assert updated_account.token_expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_refresh_oauth_token_invalid_account(self, db: Session):
        """Test refreshing token for non-existent account"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.refresh_oauth_token("nonexistent-account-id")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_oauth_token_no_refresh_token(self, db: Session, oauth_provider: OAuthProvider):
        """Test refreshing token when account has no refresh token"""
        # Create user and OAuth account without refresh token
        org = Organization(name="Test Org 2", slug="test-org-2")
        db.add(org)
        db.flush()

        user = User(
            email="norefresh@example.com",
            password_hash=None,
            organization_id=org.id
        )
        db.add(user)
        db.flush()

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider_id=oauth_provider.id,
            provider_user_id="test-user-no-refresh",
            access_token="encrypted_access_token",
            refresh_token=None  # No refresh token
        )
        db.add(oauth_account)
        db.commit()

        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.refresh_oauth_token(oauth_account.id)

        assert "No refresh token available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_valid_access_token_not_expired(self, db: Session, user_with_oauth):
        """Test getting valid access token when current token is not expired"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Get original access token
        original_access, _ = service.get_decrypted_tokens(oauth_account)

        # Get valid access token (should not refresh since not expired)
        valid_token = await service.get_valid_access_token(oauth_account.id)

        # Should return the same token (no refresh needed)
        assert valid_token == original_access

    @pytest.mark.asyncio
    async def test_get_valid_access_token_auto_refresh(self, db: Session, user_with_oauth):
        """Test getting valid access token automatically refreshes expired tokens"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Get original token
        original_access, _ = service.get_decrypted_tokens(oauth_account)

        # Set token to expired
        oauth_account.token_expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        # Get valid access token (should auto-refresh)
        valid_token = await service.get_valid_access_token(oauth_account.id)

        # Should be a different token (refreshed)
        assert valid_token != original_access
        assert valid_token.startswith("mock_access_token_")

        # Verify database was updated
        db.refresh(oauth_account)
        new_access, _ = service.get_decrypted_tokens(oauth_account)
        assert new_access == valid_token

        # Token expiration should be updated
        assert oauth_account.token_expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_get_valid_access_token_proactive_refresh(self, db: Session, user_with_oauth):
        """Test getting valid access token proactively refreshes soon-to-expire tokens"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Get original token
        original_access, _ = service.get_decrypted_tokens(oauth_account)

        # Set token to expire in 2 minutes (within default 5-minute buffer)
        oauth_account.token_expires_at = datetime.utcnow() + timedelta(minutes=2)
        db.commit()

        # Get valid access token (should proactively refresh)
        valid_token = await service.get_valid_access_token(oauth_account.id)

        # Should be a different token (refreshed)
        assert valid_token != original_access

        # Token expiration should be extended
        db.refresh(oauth_account)
        assert oauth_account.token_expires_at > datetime.utcnow() + timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_get_valid_access_token_invalid_account(self, db: Session):
        """Test getting valid access token for non-existent account"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.get_valid_access_token("nonexistent-account-id")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_preserves_encryption(self, db: Session, user_with_oauth):
        """Test that refreshed tokens are properly encrypted in database"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Refresh the token
        await service.refresh_oauth_token(oauth_account.id)

        # Verify tokens in database are still encrypted (base64-encoded)
        db.refresh(oauth_account)
        import base64

        try:
            base64.urlsafe_b64decode(oauth_account.access_token.encode())
            base64.urlsafe_b64decode(oauth_account.refresh_token.encode())
        except Exception:
            pytest.fail("Refreshed tokens are not properly encrypted")

        # Verify they can be decrypted
        access, refresh = service.get_decrypted_tokens(oauth_account)
        assert access.startswith("mock_access_token_")
        assert refresh.startswith("mock_refresh_token_")
