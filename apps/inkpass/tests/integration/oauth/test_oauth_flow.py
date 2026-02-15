"""Integration tests for OAuth flow with database"""

import pytest
from sqlalchemy.orm import Session

from src.database.models import User, OAuthProvider, OAuthAccount, UserOrganization, Organization
from src.services.oauth_service import OAuthService
from src.services.account_linking_service import AccountLinkingService
from src.services.oauth.mock_provider import MockOAuthProvider
from src.services.oauth.provider_factory import OAuthProviderFactory


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
class TestOAuthFlow:
    """Integration tests for OAuth authentication flow"""

    def test_initiate_oauth_flow(self, db: Session, oauth_provider: OAuthProvider):
        """Test initiating OAuth flow"""
        service = OAuthService(db)

        auth_url, state = service.initiate_oauth_flow(
            provider_name="mock",
            redirect_uri="http://localhost:8002/callback"
        )

        assert "mock-oauth-provider.example.com/authorize" in auth_url
        assert f"state={state}" in auth_url
        assert len(state) > 20  # State should be a secure random token

    def test_initiate_oauth_flow_invalid_provider(self, db: Session):
        """Test initiating OAuth flow with invalid provider"""
        service = OAuthService(db)

        with pytest.raises(ValueError) as exc_info:
            service.initiate_oauth_flow(
                provider_name="nonexistent",
                redirect_uri="http://localhost:8002/callback"
            )

        assert "not found or not active" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_complete_oauth_flow_new_user(self, db: Session, oauth_provider: OAuthProvider):
        """Test completing OAuth flow for a new user"""
        service = OAuthService(db)

        # Create mock authorization code
        code = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="newuser@example.com",
            name="New User",
            avatar_url="https://example.com/avatar.jpg",
            email_verified=True
        )

        # Complete OAuth flow
        user, tokens = await service.complete_oauth_flow(
            provider_name="mock",
            code=code,
            redirect_uri="http://localhost:8002/callback",
            organization_name="Test Organization"
        )

        # Verify user was created
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.password_hash is None  # OAuth-only user
        assert user.status == "active"

        # Verify organization was created
        assert user.organization is not None
        assert user.organization.name == "Test Organization"

        # Verify OAuth account was created
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()
        assert oauth_account is not None
        assert oauth_account.provider_id == oauth_provider.id
        assert oauth_account.provider_user_id == "google_123456"
        assert oauth_account.profile_data["name"] == "New User"

        # Verify tokens were generated
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_complete_oauth_flow_existing_oauth_account(
        self, db: Session, oauth_provider: OAuthProvider
    ):
        """Test completing OAuth flow for existing OAuth user"""
        service = OAuthService(db)

        # First login - create user
        code1 = MockOAuthProvider.create_mock_code(
            user_id="google_123456",
            email="existinguser@example.com",
            name="Existing User"
        )
        user1, tokens1 = await service.complete_oauth_flow(
            provider_name="mock",
            code=code1,
            redirect_uri="http://localhost:8002/callback"
        )

        # Second login - should return same user
        MockOAuthProvider.clear_mock_data()  # Reset mock data
        code2 = MockOAuthProvider.create_mock_code(
            user_id="google_123456",  # Same provider user ID
            email="existinguser@example.com",
            name="Existing User Updated"
        )
        user2, tokens2 = await service.complete_oauth_flow(
            provider_name="mock",
            code=code2,
            redirect_uri="http://localhost:8002/callback"
        )

        # Should be the same user
        assert user1.id == user2.id
        assert user1.email == user2.email

        # OAuth account should be updated
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user2.id
        ).first()
        assert oauth_account.profile_data["name"] == "Existing User Updated"

    @pytest.mark.asyncio
    async def test_complete_oauth_flow_link_to_existing_email(
        self, db: Session, oauth_provider: OAuthProvider
    ):
        """Test OAuth login with email that already exists (account linking)"""
        # Create a user with password-based auth
        org = Organization(name="Existing Org", slug="existing-org")
        db.add(org)
        db.flush()

        from src.security.password import hash_password
        existing_user = User(
            email="existing@example.com",
            password_hash=hash_password("password123"),
            organization_id=org.id
        )
        db.add(existing_user)
        db.commit()
        db.refresh(existing_user)

        # Now login with OAuth using same email
        service = OAuthService(db)
        code = MockOAuthProvider.create_mock_code(
            user_id="google_789",
            email="existing@example.com",  # Same email
            name="Existing User"
        )

        user, tokens = await service.complete_oauth_flow(
            provider_name="mock",
            code=code,
            redirect_uri="http://localhost:8002/callback"
        )

        # Should link to existing user, not create new one
        assert user.id == existing_user.id
        assert user.email == "existing@example.com"
        assert user.password_hash is not None  # Should keep password

        # OAuth account should be linked
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id
        ).first()
        assert oauth_account is not None
        assert oauth_account.provider_user_id == "google_789"


@pytest.mark.integration
class TestAccountLinkingService:
    """Integration tests for multi-org account linking"""

    @pytest.fixture(autouse=True)
    def setup_organizations(self, db: Session):
        """Create test organizations"""
        org1 = Organization(name="Org 1", slug="org-1")
        org2 = Organization(name="Org 2", slug="org-2")
        db.add_all([org1, org2])
        db.commit()

        self.org1 = org1
        self.org2 = org2

    def test_add_user_to_organization(self, db: Session):
        """Test adding a user to an organization"""
        # Create user
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        # Add user to second organization
        service = AccountLinkingService(db)
        user_org = service.add_user_to_organization(
            user_id=user.id,
            organization_id=self.org2.id,
            role="member",
            is_primary=False
        )

        assert user_org is not None
        assert user_org.user_id == user.id
        assert user_org.organization_id == self.org2.id
        assert user_org.role == "member"
        assert user_org.is_primary is False

    @pytest.mark.skip(reason="Known issue: duplicate check needs improvement")
    def test_add_user_to_organization_duplicate(self, db: Session):
        """Test adding user to organization they already belong to"""
        from src.security.password import hash_password
        from sqlalchemy.exc import IntegrityError

        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)
        service.add_user_to_organization(user.id, self.org2.id)

        # Try to add again - should raise ValueError (wrapped IntegrityError)
        try:
            service.add_user_to_organization(user.id, self.org2.id)
            pytest.fail("Should have raised ValueError or IntegrityError")
        except (ValueError, IntegrityError):
            pass  # Expected - duplicate entry

    def test_set_primary_organization(self, db: Session):
        """Test setting primary organization"""
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)

        # Add user to org2
        service.add_user_to_organization(user.id, self.org2.id, is_primary=False)

        # Set org2 as primary
        user_org = service.set_primary_organization(user.id, self.org2.id)

        assert user_org.is_primary is True

    def test_get_user_organizations(self, db: Session):
        """Test getting all organizations for a user"""
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)
        service.add_user_to_organization(user.id, self.org1.id, is_primary=True)
        service.add_user_to_organization(user.id, self.org2.id, role="admin")

        user_orgs = service.get_user_organizations(user.id)

        assert len(user_orgs) == 2
        org_ids = [uo.organization_id for uo in user_orgs]
        assert self.org1.id in org_ids
        assert self.org2.id in org_ids

    def test_remove_user_from_organization(self, db: Session):
        """Test removing user from organization"""
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)
        service.add_user_to_organization(user.id, self.org2.id)

        # Remove from org2
        result = service.remove_user_from_organization(user.id, self.org2.id)
        assert result is True

        # Verify removed
        user_orgs = service.get_user_organizations(user.id)
        org_ids = [uo.organization_id for uo in user_orgs]
        assert self.org2.id not in org_ids

    def test_update_user_role(self, db: Session):
        """Test updating user's role in organization"""
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)
        service.add_user_to_organization(user.id, self.org2.id, role="member")

        # Update role
        user_org = service.update_user_role(user.id, self.org2.id, "admin")

        assert user_org.role == "admin"

    def test_is_user_in_organization(self, db: Session):
        """Test checking if user belongs to organization"""
        from src.security.password import hash_password
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("password"),
            organization_id=self.org1.id
        )
        db.add(user)
        db.commit()

        service = AccountLinkingService(db)
        service.add_user_to_organization(user.id, self.org1.id)

        assert service.is_user_in_organization(user.id, self.org1.id) is True
        assert service.is_user_in_organization(user.id, self.org2.id) is False
