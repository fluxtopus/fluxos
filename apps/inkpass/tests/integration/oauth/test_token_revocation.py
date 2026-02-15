"""Integration tests for OAuth token revocation"""

import pytest
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

    # Create user with password (so they have alternative auth method)
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("password123"),
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
class TestTokenRevocation:
    """Integration tests for OAuth token revocation"""

    @pytest.mark.asyncio
    async def test_revoke_oauth_token(self, db: Session, user_with_oauth):
        """Test revoking OAuth tokens for an account"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Verify tokens exist before revocation
        assert oauth_account.access_token is not None
        assert oauth_account.refresh_token is not None
        assert oauth_account.token_expires_at is not None

        # Revoke the tokens
        result = await service.revoke_oauth_token(oauth_account.id)

        assert result is True

        # Verify tokens were cleared
        db.refresh(oauth_account)
        assert oauth_account.access_token is None
        assert oauth_account.refresh_token is None
        assert oauth_account.token_expires_at is None

    @pytest.mark.asyncio
    async def test_revoke_oauth_token_invalid_account(self, db: Session):
        """Test revoking tokens for non-existent account"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.revoke_oauth_token("nonexistent-account-id")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_revoke_oauth_token_already_revoked(self, db: Session, user_with_oauth):
        """Test revoking tokens that are already revoked"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Revoke once
        await service.revoke_oauth_token(oauth_account.id)

        # Revoke again (should still succeed)
        result = await service.revoke_oauth_token(oauth_account.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_oauth_account(self, db: Session, user_with_oauth):
        """Test completely disconnecting an OAuth account"""
        user, oauth_account = user_with_oauth
        service = OAuthService(db)
        oauth_account_id = oauth_account.id

        # Disconnect the account
        result = await service.disconnect_oauth_account(oauth_account_id)

        assert result is True

        # Verify OAuth account no longer exists
        deleted_account = db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account_id
        ).first()
        assert deleted_account is None

        # Verify user still exists (not cascade deleted)
        existing_user = db.query(User).filter(User.id == user.id).first()
        assert existing_user is not None

    @pytest.mark.asyncio
    async def test_disconnect_only_auth_method_fails(self, db: Session, oauth_provider: OAuthProvider):
        """Test disconnecting the only auth method is prevented"""
        # Create user with ONLY OAuth (no password)
        org = Organization(name="OAuth Only Org", slug="oauth-only-org")
        db.add(org)
        db.flush()

        user = User(
            email="oauthonly@example.com",
            password_hash=None,  # No password
            organization_id=org.id
        )
        db.add(user)
        db.flush()

        # Create OAuth account
        code = MockOAuthProvider.create_mock_code(
            user_id="oauth_only_user",
            email="oauthonly@example.com",
            name="OAuth Only User"
        )

        service = OAuthService(db)
        _, _ = await service.complete_oauth_flow(
            provider_name="mock",
            code=code,
            redirect_uri="http://localhost:8002/callback"
        )

        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()

        # Try to disconnect (should fail - it's the only auth method)
        with pytest.raises(ValueError) as exc_info:
            await service.disconnect_oauth_account(oauth_account.id)

        assert "only authentication method" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_disconnect_with_multiple_oauth_accounts(self, db: Session, oauth_provider: OAuthProvider):
        """Test disconnecting one OAuth account when user has multiple"""
        # Create user with no password
        org = Organization(name="Multi OAuth Org", slug="multi-oauth-org")
        db.add(org)
        db.flush()

        user = User(
            email="multioauth@example.com",
            password_hash=None,
            organization_id=org.id
        )
        db.add(user)
        db.flush()

        service = OAuthService(db)

        # Add first OAuth account (Google)
        code1 = MockOAuthProvider.create_mock_code(
            user_id="google_user_123",
            email="multioauth@example.com",
            name="Multi OAuth User"
        )
        await service.complete_oauth_flow(
            provider_name="mock",
            code=code1,
            redirect_uri="http://localhost:8002/callback"
        )

        oauth_account1 = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()

        # Add second OAuth account (simulate different provider)
        MockOAuthProvider.clear_mock_data()
        oauth_account2 = OAuthAccount(
            user_id=user.id,
            provider_id=oauth_provider.id,
            provider_user_id="apple_user_456",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token"
        )
        db.add(oauth_account2)
        db.commit()

        # Should be able to disconnect first account (has second account)
        result = await service.disconnect_oauth_account(oauth_account1.id)

        assert result is True

        # Verify first account deleted but second remains
        assert db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account1.id
        ).first() is None

        assert db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account2.id
        ).first() is not None

    @pytest.mark.asyncio
    async def test_disconnect_oauth_account_invalid_id(self, db: Session):
        """Test disconnecting non-existent OAuth account"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.disconnect_oauth_account("nonexistent-id")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_revoke_all_user_oauth_tokens(self, db: Session, oauth_provider: OAuthProvider):
        """Test revoking all OAuth tokens for a user"""
        # Create user with multiple OAuth accounts
        org = Organization(name="Multi Revoke Org", slug="multi-revoke-org")
        db.add(org)
        db.flush()

        user = User(
            email="multirevoke@example.com",
            password_hash=hash_password("password123"),
            organization_id=org.id
        )
        db.add(user)
        db.flush()

        service = OAuthService(db)

        # Add first OAuth account
        code1 = MockOAuthProvider.create_mock_code(
            user_id="user_account_1",
            email="multirevoke@example.com",
            name="User Account 1"
        )
        await service.complete_oauth_flow(
            provider_name="mock",
            code=code1,
            redirect_uri="http://localhost:8002/callback"
        )

        # Add second OAuth account
        MockOAuthProvider.clear_mock_data()
        code2 = MockOAuthProvider.create_mock_code(
            user_id="user_account_2",
            email="multirevoke@example.com",
            name="User Account 2"
        )
        # Create second OAuth account manually
        oauth_account2 = OAuthAccount(
            user_id=user.id,
            provider_id=oauth_provider.id,
            provider_user_id="user_account_2",
            access_token="encrypted_token_2",
            refresh_token="encrypted_refresh_2"
        )
        db.add(oauth_account2)
        db.commit()

        # Verify both accounts have tokens
        oauth_accounts_before = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).all()
        assert len(oauth_accounts_before) == 2
        assert all(acc.access_token is not None for acc in oauth_accounts_before)

        # Revoke all tokens
        revoked_count = await service.revoke_all_user_oauth_tokens(user.id)

        assert revoked_count == 2

        # Verify all tokens cleared but accounts still exist
        oauth_accounts_after = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).all()
        assert len(oauth_accounts_after) == 2
        assert all(acc.access_token is None for acc in oauth_accounts_after)
        assert all(acc.refresh_token is None for acc in oauth_accounts_after)

    @pytest.mark.asyncio
    async def test_revoke_all_user_oauth_tokens_invalid_user(self, db: Session):
        """Test revoking tokens for non-existent user"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.revoke_all_user_oauth_tokens("nonexistent-user-id")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_revoke_all_user_oauth_tokens_no_accounts(self, db: Session):
        """Test revoking tokens for user with no OAuth accounts"""
        # Create user with no OAuth accounts
        org = Organization(name="No OAuth Org", slug="no-oauth-org")
        db.add(org)
        db.flush()

        user = User(
            email="nooauth@example.com",
            password_hash=hash_password("password123"),
            organization_id=org.id
        )
        db.add(user)
        db.commit()

        service = OAuthService(db)

        # Revoke (should succeed with 0 count)
        revoked_count = await service.revoke_all_user_oauth_tokens(user.id)

        assert revoked_count == 0

    @pytest.mark.asyncio
    async def test_revoke_updates_timestamp(self, db: Session, user_with_oauth):
        """Test that revocation updates the updated_at timestamp"""
        _, oauth_account = user_with_oauth
        service = OAuthService(db)

        # Get original timestamp
        original_updated_at = oauth_account.updated_at

        # Wait a moment to ensure timestamp difference
        import time
        time.sleep(0.1)

        # Revoke tokens
        await service.revoke_oauth_token(oauth_account.id)

        # Verify timestamp was updated
        db.refresh(oauth_account)
        assert oauth_account.updated_at > original_updated_at
