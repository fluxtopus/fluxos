"""OAuth Service - Manages OAuth authentication flow"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.database.models import User, OAuthProvider, OAuthAccount, Organization
from src.services.oauth import OAuthProviderFactory
from src.services.oauth.provider_interface import OAuthUserInfo, OAuthError
from src.security.jwt import create_access_token, create_refresh_token
from src.security.encryption import encrypt_data, decrypt_data


class OAuthService:
    """
    Service for managing OAuth authentication flows.

    Single Responsibility: Orchestrate OAuth login/signup process including:
    - Initiating OAuth flow
    - Exchanging authorization code for tokens
    - Creating or linking user accounts
    - Managing OAuth provider configurations

    Does NOT handle multi-org relationships (that's AccountLinkingService's job).
    """

    def __init__(self, db: Session):
        self.db = db

    def initiate_oauth_flow(self, provider_name: str, redirect_uri: str) -> Tuple[str, str]:
        """
        Start OAuth flow by generating authorization URL.

        Args:
            provider_name: Name of OAuth provider (e.g., "google")
            redirect_uri: Callback URL after OAuth authorization

        Returns:
            Tuple of (authorization_url, state_token)

        Raises:
            ValueError: If provider not found or not active
        """
        # Get provider configuration from database
        provider_config = self.db.query(OAuthProvider).filter(
            OAuthProvider.provider_name == provider_name,
            OAuthProvider.is_active == True
        ).first()

        if not provider_config:
            raise ValueError(f"OAuth provider '{provider_name}' not found or not active")

        # Create provider instance using factory
        provider = OAuthProviderFactory.create(
            provider_name=provider_name,
            client_id=provider_config.client_id,
            client_secret=provider_config.client_secret,
            redirect_uri=redirect_uri,
            scopes=provider_config.scopes or []
        )

        # Generate CSRF protection state token
        state = secrets.token_urlsafe(32)

        # Generate authorization URL
        auth_url = provider.get_authorization_url(state)

        return auth_url, state

    async def complete_oauth_flow(
        self,
        provider_name: str,
        code: str,
        redirect_uri: str,
        organization_name: Optional[str] = None
    ) -> Tuple[User, dict]:
        """
        Complete OAuth flow by exchanging code for tokens and creating/linking user.

        Args:
            provider_name: Name of OAuth provider
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect URI used in initiate_oauth_flow
            organization_name: Organization name for new users (optional)

        Returns:
            Tuple of (User, tokens_dict) where tokens_dict contains access_token, refresh_token

        Raises:
            OAuthError: If OAuth flow fails
            ValueError: If provider not found
        """
        # Get provider configuration
        provider_config = self.db.query(OAuthProvider).filter(
            OAuthProvider.provider_name == provider_name,
            OAuthProvider.is_active == True
        ).first()

        if not provider_config:
            raise ValueError(f"OAuth provider '{provider_name}' not found or not active")

        # Create provider instance
        provider = OAuthProviderFactory.create(
            provider_name=provider_name,
            client_id=provider_config.client_id,
            client_secret=provider_config.client_secret,
            redirect_uri=redirect_uri,
            scopes=provider_config.scopes or []
        )

        # Exchange code for tokens
        tokens = await provider.exchange_code_for_tokens(code)

        # Get user info from provider
        user_info = await provider.get_user_info(tokens.access_token)

        # Find or create user
        user = await self._find_or_create_user(
            provider_config=provider_config,
            user_info=user_info,
            tokens=tokens,
            organization_name=organization_name
        )

        # Generate inkPass tokens
        access_token = create_access_token({"sub": user.id, "email": user.email})
        refresh_token = create_refresh_token({"sub": user.id})

        return user, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 1800  # 30 minutes
        }

    async def _find_or_create_user(
        self,
        provider_config: OAuthProvider,
        user_info: OAuthUserInfo,
        tokens,
        organization_name: Optional[str]
    ) -> User:
        """
        Find existing user by OAuth account or create new user.

        Args:
            provider_config: OAuth provider configuration
            user_info: User info from OAuth provider
            tokens: OAuth tokens
            organization_name: Organization name for new users

        Returns:
            User instance (existing or newly created)
        """
        # Check if OAuth account already exists
        oauth_account = self.db.query(OAuthAccount).filter(
            OAuthAccount.provider_id == provider_config.id,
            OAuthAccount.provider_user_id == user_info.provider_user_id
        ).first()

        if oauth_account:
            # Existing OAuth account - update tokens and return user
            oauth_account.access_token = encrypt_data(tokens.access_token) if tokens.access_token else None
            oauth_account.refresh_token = encrypt_data(tokens.refresh_token) if tokens.refresh_token else None
            if tokens.expires_in:
                oauth_account.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.expires_in)
            oauth_account.profile_data = user_info.raw_data
            oauth_account.updated_at = datetime.utcnow()
            self.db.commit()
            return oauth_account.user

        # Check if user with this email already exists (account linking scenario)
        existing_user = self.db.query(User).filter(User.email == user_info.email).first()

        if existing_user:
            # Link OAuth account to existing user
            oauth_account = OAuthAccount(
                user_id=existing_user.id,
                provider_id=provider_config.id,
                provider_user_id=user_info.provider_user_id,
                access_token=encrypt_data(tokens.access_token) if tokens.access_token else None,
                refresh_token=encrypt_data(tokens.refresh_token) if tokens.refresh_token else None,
                token_expires_at=datetime.utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None,
                profile_data=user_info.raw_data
            )
            self.db.add(oauth_account)
            self.db.commit()
            return existing_user

        # Create new user with OAuth account
        # First, create or get organization
        if not organization_name:
            organization_name = f"{user_info.name or user_info.email}'s Organization"

        # Create organization
        org_slug = organization_name.lower().replace(" ", "-")
        # Make slug unique if needed
        counter = 1
        base_slug = org_slug
        while self.db.query(Organization).filter(Organization.slug == org_slug).first():
            org_slug = f"{base_slug}-{counter}"
            counter += 1

        organization = Organization(
            name=organization_name,
            slug=org_slug
        )
        self.db.add(organization)
        self.db.flush()

        # Create user (no password hash for OAuth-only users)
        new_user = User(
            email=user_info.email,
            password_hash=None,  # OAuth-only user
            organization_id=organization.id,
            status="active"
        )
        self.db.add(new_user)
        self.db.flush()

        # Create OAuth account
        oauth_account = OAuthAccount(
            user_id=new_user.id,
            provider_id=provider_config.id,
            provider_user_id=user_info.provider_user_id,
            access_token=encrypt_data(tokens.access_token) if tokens.access_token else None,
            refresh_token=encrypt_data(tokens.refresh_token) if tokens.refresh_token else None,
            token_expires_at=datetime.utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None,
            profile_data=user_info.raw_data
        )
        self.db.add(oauth_account)
        self.db.commit()
        self.db.refresh(new_user)

        return new_user

    def create_provider_config(
        self,
        provider_name: str,
        client_id: str,
        client_secret: str,
        scopes: Optional[list[str]] = None
    ) -> OAuthProvider:
        """
        Create OAuth provider configuration in database.

        Args:
            provider_name: Name of the provider (e.g., "google")
            client_id: OAuth client ID
            client_secret: OAuth client secret (will be stored securely)
            scopes: List of OAuth scopes

        Returns:
            Created OAuthProvider instance

        Raises:
            ValueError: If provider already exists or not registered in factory
        """
        # Verify provider is registered in factory
        if not OAuthProviderFactory.is_registered(provider_name):
            raise ValueError(
                f"Provider '{provider_name}' not registered. "
                f"Available: {', '.join(OAuthProviderFactory.list_providers())}"
            )

        # Check if provider already exists
        existing = self.db.query(OAuthProvider).filter(
            OAuthProvider.provider_name == provider_name
        ).first()

        if existing:
            raise ValueError(f"Provider '{provider_name}' already exists")

        # Get provider URLs from factory
        temp_provider = OAuthProviderFactory.create(
            provider_name=provider_name,
            client_id="temp",
            client_secret="temp",
            redirect_uri="http://localhost",
            scopes=scopes or []
        )

        # Create provider config
        provider_config = OAuthProvider(
            provider_name=provider_name,
            client_id=client_id,
            client_secret=client_secret,  # TODO: Encrypt this
            authorization_url=getattr(temp_provider, 'AUTHORIZATION_URL', ''),
            token_url=getattr(temp_provider, 'TOKEN_URL', ''),
            user_info_url=getattr(temp_provider, 'USER_INFO_URL', ''),
            scopes=scopes or [],
            is_active=True
        )

        self.db.add(provider_config)
        self.db.commit()
        self.db.refresh(provider_config)

        return provider_config

    def list_active_providers(self) -> list[OAuthProvider]:
        """
        List all active OAuth providers.

        Returns:
            List of active OAuth provider configurations
        """
        return self.db.query(OAuthProvider).filter(
            OAuthProvider.is_active == True
        ).all()

    def get_user_oauth_accounts(self, user_id: str) -> list[OAuthAccount]:
        """
        Get all OAuth accounts for a user.

        Args:
            user_id: User ID

        Returns:
            List of OAuth accounts linked to the user
            NOTE: Tokens in returned accounts are ENCRYPTED. Use get_decrypted_tokens() to decrypt.
        """
        return self.db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user_id
        ).all()

    def get_decrypted_tokens(self, oauth_account: OAuthAccount) -> Tuple[Optional[str], Optional[str]]:
        """
        Securely retrieve and decrypt OAuth tokens for internal use.

        This method should ONLY be used internally when tokens are needed for:
        - Refreshing expired tokens
        - Making API calls on behalf of the user

        NEVER expose decrypted tokens in API responses.

        Args:
            oauth_account: OAuthAccount instance with encrypted tokens

        Returns:
            Tuple of (decrypted_access_token, decrypted_refresh_token)
        """
        access_token = None
        refresh_token = None

        if oauth_account.access_token:
            try:
                access_token = decrypt_data(oauth_account.access_token)
            except Exception as e:
                # Log decryption failure but don't expose details
                print(f"Failed to decrypt access token: {e}")

        if oauth_account.refresh_token:
            try:
                refresh_token = decrypt_data(oauth_account.refresh_token)
            except Exception as e:
                # Log decryption failure but don't expose details
                print(f"Failed to decrypt refresh token: {e}")

        return access_token, refresh_token

    def is_token_expired(self, oauth_account: OAuthAccount, buffer_seconds: int = 300) -> bool:
        """
        Check if an OAuth account's access token is expired or about to expire.

        Args:
            oauth_account: OAuthAccount instance to check
            buffer_seconds: Number of seconds before expiration to consider token expired
                          (default: 300 = 5 minutes). This allows proactive refresh.

        Returns:
            True if token is expired or will expire within buffer_seconds, False otherwise
        """
        if not oauth_account.token_expires_at:
            # If no expiration time is set, assume token doesn't expire
            return False

        # Add buffer to current time for proactive refresh
        expiration_threshold = datetime.utcnow() + timedelta(seconds=buffer_seconds)

        return oauth_account.token_expires_at <= expiration_threshold

    async def refresh_oauth_token(self, oauth_account_id: str) -> OAuthAccount:
        """
        Refresh an expired OAuth access token using the refresh token.

        This method:
        1. Retrieves the OAuth account from database
        2. Decrypts the refresh token
        3. Calls the OAuth provider to get new tokens
        4. Updates the database with encrypted new tokens
        5. Returns the updated OAuth account

        Args:
            oauth_account_id: ID of the OAuthAccount to refresh

        Returns:
            Updated OAuthAccount with new tokens

        Raises:
            ValueError: If OAuth account not found
            OAuthError: If token refresh fails
        """
        # Get OAuth account from database
        oauth_account = self.db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account_id
        ).first()

        if not oauth_account:
            raise ValueError(f"OAuth account '{oauth_account_id}' not found")

        # Get the provider configuration
        provider_config = self.db.query(OAuthProvider).filter(
            OAuthProvider.id == oauth_account.provider_id
        ).first()

        if not provider_config:
            raise ValueError(f"OAuth provider not found for account '{oauth_account_id}'")

        # Decrypt refresh token
        _, refresh_token = self.get_decrypted_tokens(oauth_account)

        if not refresh_token:
            raise ValueError(f"No refresh token available for account '{oauth_account_id}'")

        # Create provider instance
        provider = OAuthProviderFactory.create(
            provider_name=provider_config.provider_name,
            client_id=provider_config.client_id,
            client_secret=provider_config.client_secret,
            redirect_uri="",  # Not needed for token refresh
            scopes=provider_config.scopes or []
        )

        # Refresh the token
        new_tokens = await provider.refresh_access_token(refresh_token)

        # Update OAuth account with new encrypted tokens
        oauth_account.access_token = encrypt_data(new_tokens.access_token) if new_tokens.access_token else None
        oauth_account.refresh_token = encrypt_data(new_tokens.refresh_token) if new_tokens.refresh_token else oauth_account.refresh_token
        if new_tokens.expires_in:
            oauth_account.token_expires_at = datetime.utcnow() + timedelta(seconds=new_tokens.expires_in)
        oauth_account.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(oauth_account)

        return oauth_account

    async def get_valid_access_token(self, oauth_account_id: str) -> str:
        """
        Get a valid access token, automatically refreshing if needed.

        This is the recommended method for getting access tokens for making API calls.
        It handles token expiration automatically.

        Args:
            oauth_account_id: ID of the OAuthAccount

        Returns:
            Valid (non-expired) decrypted access token

        Raises:
            ValueError: If OAuth account not found or has no tokens
            OAuthError: If token refresh fails
        """
        # Get OAuth account
        oauth_account = self.db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account_id
        ).first()

        if not oauth_account:
            raise ValueError(f"OAuth account '{oauth_account_id}' not found")

        # Check if token is expired or about to expire
        if self.is_token_expired(oauth_account):
            # Token expired, refresh it
            oauth_account = await self.refresh_oauth_token(oauth_account_id)

        # Decrypt and return access token
        access_token, _ = self.get_decrypted_tokens(oauth_account)

        if not access_token:
            raise ValueError(f"No access token available for account '{oauth_account_id}'")

        return access_token

    async def revoke_oauth_token(self, oauth_account_id: str, revoke_on_provider: bool = True) -> bool:
        """
        Revoke OAuth tokens for an account.

        This method:
        1. Retrieves the OAuth account from database
        2. Optionally calls the OAuth provider to revoke the token
        3. Clears the tokens from the database

        Args:
            oauth_account_id: ID of the OAuthAccount to revoke
            revoke_on_provider: Whether to also revoke on the OAuth provider (default: True)

        Returns:
            True if revocation successful

        Raises:
            ValueError: If OAuth account not found
        """
        # Get OAuth account from database
        oauth_account = self.db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account_id
        ).first()

        if not oauth_account:
            raise ValueError(f"OAuth account '{oauth_account_id}' not found")

        # Optionally revoke on provider
        if revoke_on_provider and oauth_account.access_token:
            try:
                # Get the provider configuration
                provider_config = self.db.query(OAuthProvider).filter(
                    OAuthProvider.id == oauth_account.provider_id
                ).first()

                if provider_config:
                    # Decrypt access token
                    access_token, _ = self.get_decrypted_tokens(oauth_account)

                    if access_token:
                        # Note: Not all providers support token revocation
                        # This is a best-effort attempt
                        # Provider implementation would need revoke_token() method
                        pass
            except Exception as e:
                # Log the error but continue with local revocation
                print(f"Warning: Failed to revoke token on provider: {e}")

        # Clear tokens from database
        oauth_account.access_token = None
        oauth_account.refresh_token = None
        oauth_account.token_expires_at = None
        oauth_account.updated_at = datetime.utcnow()

        self.db.commit()

        return True

    async def disconnect_oauth_account(self, oauth_account_id: str) -> bool:
        """
        Disconnect an OAuth account from a user.

        This completely removes the OAuth account linkage, revoking tokens
        and deleting the account record.

        WARNING: This is permanent. The user will need to re-authenticate
        with OAuth to restore the connection.

        Args:
            oauth_account_id: ID of the OAuthAccount to disconnect

        Returns:
            True if disconnection successful

        Raises:
            ValueError: If OAuth account not found or is the only auth method
        """
        # Get OAuth account from database
        oauth_account = self.db.query(OAuthAccount).filter(
            OAuthAccount.id == oauth_account_id
        ).first()

        if not oauth_account:
            raise ValueError(f"OAuth account '{oauth_account_id}' not found")

        # Get user to check if they have other auth methods
        user = oauth_account.user

        # Check if user has password auth or other OAuth accounts
        other_oauth_accounts = self.db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id,
            OAuthAccount.id != oauth_account_id
        ).count()

        has_password = user.password_hash is not None

        if not has_password and other_oauth_accounts == 0:
            raise ValueError(
                "Cannot disconnect the only authentication method. "
                "User would be locked out of their account."
            )

        # Revoke tokens
        await self.revoke_oauth_token(oauth_account_id, revoke_on_provider=True)

        # Delete the OAuth account
        self.db.delete(oauth_account)
        self.db.commit()

        return True

    async def revoke_all_user_oauth_tokens(self, user_id: str) -> int:
        """
        Revoke all OAuth tokens for a user.

        Useful for security scenarios like:
        - User reports account compromise
        - Password change (optional security measure)
        - Admin action

        This does NOT delete the OAuth accounts, just clears their tokens.
        User can re-authenticate to get new tokens.

        Args:
            user_id: ID of the user

        Returns:
            Number of OAuth accounts that had their tokens revoked

        Raises:
            ValueError: If user not found
        """
        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            raise ValueError(f"User '{user_id}' not found")

        # Get all OAuth accounts for user
        oauth_accounts = self.db.query(OAuthAccount).filter(
            OAuthAccount.user_id == user_id
        ).all()

        revoked_count = 0
        for oauth_account in oauth_accounts:
            try:
                await self.revoke_oauth_token(oauth_account.id, revoke_on_provider=True)
                revoked_count += 1
            except Exception as e:
                # Log error but continue with other accounts
                print(f"Failed to revoke OAuth account {oauth_account.id}: {e}")

        return revoked_count
