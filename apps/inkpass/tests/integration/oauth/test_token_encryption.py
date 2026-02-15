"""Integration tests for OAuth token encryption"""

import pytest
from sqlalchemy.orm import Session

from src.database.models import OAuthProvider, OAuthAccount
from src.services.oauth_service import OAuthService
from src.services.oauth.mock_provider import MockOAuthProvider
from src.services.oauth.provider_factory import OAuthProviderFactory
from src.security.encryption import decrypt_data


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


@pytest.mark.integration
class TestOAuthTokenEncryption:
    """Integration tests for OAuth token encryption at rest"""

    @pytest.mark.asyncio
    async def test_tokens_are_encrypted_in_database(self, db: Session, oauth_provider: OAuthProvider):
        """Verify that OAuth tokens are encrypted when stored in database"""
        service = OAuthService(db)

        # Create mock authorization code with known token values
        code = MockOAuthProvider.create_mock_code(
            user_id="test_user_123",
            email="encryption_test@example.com",
            name="Encryption Test User"
        )

        # Complete OAuth flow
        user, tokens = await service.complete_oauth_flow(
            provider_name="mock",
            code=code,
            redirect_uri="http://localhost:8002/callback"
        )

        # Get OAuth account from database
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()

        assert oauth_account is not None

        # Verify tokens are stored (not None)
        assert oauth_account.access_token is not None
        assert oauth_account.refresh_token is not None

        # Verify stored tokens are base64-encoded (characteristic of encrypted data)
        import base64
        try:
            base64.urlsafe_b64decode(oauth_account.access_token.encode())
            base64.urlsafe_b64decode(oauth_account.refresh_token.encode())
            # If we get here, tokens are base64-encoded (good sign of encryption)
        except Exception:
            pytest.fail("Stored tokens are not properly base64-encoded")

        # Verify tokens CAN be decrypted and start with expected prefix
        decrypted_access, decrypted_refresh = service.get_decrypted_tokens(oauth_account)

        # MockProvider generates tokens with this prefix
        assert decrypted_access.startswith("mock_access_token_")
        assert decrypted_refresh.startswith("mock_refresh_token_")

        # Verify decrypted tokens are different from encrypted ones (shows encryption worked)
        assert decrypted_access != oauth_account.access_token
        assert decrypted_refresh != oauth_account.refresh_token

    @pytest.mark.asyncio
    async def test_token_update_maintains_encryption(self, db: Session, oauth_provider: OAuthProvider):
        """Verify that token updates maintain encryption"""
        service = OAuthService(db)

        # First login
        code1 = MockOAuthProvider.create_mock_code(
            user_id="user_456",
            email="update_test@example.com",
            name="Update Test"
        )
        user1, _ = await service.complete_oauth_flow(
            provider_name="mock",
            code=code1,
            redirect_uri="http://localhost:8002/callback"
        )

        # Get OAuth account after first login
        oauth_account1 = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user1.id
        ).first()
        first_encrypted_token = oauth_account1.access_token

        # Second login (token update)
        MockOAuthProvider.clear_mock_data()
        code2 = MockOAuthProvider.create_mock_code(
            user_id="user_456",  # Same user ID
            email="update_test@example.com",
            name="Update Test"
        )
        user2, _ = await service.complete_oauth_flow(
            provider_name="mock",
            code=code2,
            redirect_uri="http://localhost:8002/callback"
        )

        # Get updated OAuth account
        db.refresh(oauth_account1)
        second_encrypted_token = oauth_account1.access_token

        # Tokens should still be encrypted (and different due to new mock data)
        assert first_encrypted_token != second_encrypted_token

        # But should decrypt correctly to mock tokens
        decrypted_access, _ = service.get_decrypted_tokens(oauth_account1)
        assert decrypted_access.startswith("mock_access_token_")

    @pytest.mark.asyncio
    async def test_account_linking_encrypts_tokens(self, db: Session, oauth_provider: OAuthProvider):
        """Verify that account linking also encrypts tokens"""
        from src.database.models import User, Organization
        from src.security.password import hash_password

        # Create existing user with password
        org = Organization(name="Test Org", slug="test-org")
        db.add(org)
        db.flush()

        existing_user = User(
            email="link_test@example.com",
            password_hash=hash_password("password123"),
            organization_id=org.id
        )
        db.add(existing_user)
        db.commit()

        # OAuth login with same email (should link accounts)
        service = OAuthService(db)
        code = MockOAuthProvider.create_mock_code(
            user_id="linked_user_789",
            email="link_test@example.com",
            name="Link Test"
        )

        user, _ = await service.complete_oauth_flow(
            provider_name="mock",
            code=code,
            redirect_uri="http://localhost:8002/callback"
        )

        # Get linked OAuth account
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()

        # Verify they decrypt correctly to mock tokens
        decrypted_access, _ = service.get_decrypted_tokens(oauth_account)
        assert decrypted_access.startswith("mock_access_token_")

        # Verify encrypted token is different from decrypted (encryption worked)
        assert decrypted_access != oauth_account.access_token

    def test_get_decrypted_tokens_handles_missing_tokens(self, db: Session, oauth_provider: OAuthProvider):
        """Verify get_decrypted_tokens handles None tokens gracefully"""
        from src.database.models import User, Organization

        # Create user and OAuth account with no tokens
        org = Organization(name="Test Org", slug="test-org-2")
        db.add(org)
        db.flush()

        user = User(
            email="notoken@example.com",
            password_hash=None,
            organization_id=org.id
        )
        db.add(user)
        db.flush()

        # Create OAuth account without tokens
        oauth_account = OAuthAccount(
            user_id=user.id,
            provider_id=oauth_provider.id,  # Use the fixture provider
            provider_user_id="test-user",
            access_token=None,
            refresh_token=None
        )
        db.add(oauth_account)
        db.commit()

        service = OAuthService(db)
        access, refresh = service.get_decrypted_tokens(oauth_account)

        assert access is None
        assert refresh is None
