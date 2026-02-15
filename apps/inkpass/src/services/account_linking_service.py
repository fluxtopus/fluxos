"""Account Linking Service - Manages multi-organization user relationships"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.database.models import User, Organization, UserOrganization


class AccountLinkingService:
    """
    Service for managing user-organization relationships.

    Single Responsibility: Handle multi-org user membership including:
    - Adding users to organizations
    - Removing users from organizations
    - Managing primary organization
    - Querying user's organizations

    This enables a single user (authenticated via OAuth or password) to belong
    to multiple organizations with different roles in each.
    """

    def __init__(self, db: Session):
        self.db = db

    def add_user_to_organization(
        self,
        user_id: str,
        organization_id: str,
        role: str = "member",
        is_primary: bool = False
    ) -> UserOrganization:
        """
        Add a user to an organization.

        Args:
            user_id: User ID
            organization_id: Organization ID
            role: User's role in the organization (default: "member")
            is_primary: Whether this is the user's primary organization

        Returns:
            UserOrganization instance

        Raises:
            ValueError: If user or organization doesn't exist
            IntegrityError: If user already belongs to organization
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User with ID '{user_id}' not found")

        # Verify organization exists
        organization = self.db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not organization:
            raise ValueError(f"Organization with ID '{organization_id}' not found")

        # If setting as primary, unset other primary organizations for this user
        if is_primary:
            self.db.query(UserOrganization).filter(
                UserOrganization.user_id == user_id,
                UserOrganization.is_primary == True
            ).update({"is_primary": False})

        # Create user-organization relationship
        user_org = UserOrganization(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            is_primary=is_primary
        )

        try:
            self.db.add(user_org)
            self.db.commit()
            self.db.refresh(user_org)
            return user_org
        except IntegrityError:
            self.db.rollback()
            raise ValueError(
                f"User '{user_id}' already belongs to organization '{organization_id}'"
            )

    def remove_user_from_organization(
        self,
        user_id: str,
        organization_id: str
    ) -> bool:
        """
        Remove a user from an organization.

        Args:
            user_id: User ID
            organization_id: Organization ID

        Returns:
            True if user was removed, False if relationship didn't exist

        Note:
            If this was the user's primary organization, they will need to set
            a new primary organization.
        """
        user_org = self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        ).first()

        if not user_org:
            return False

        self.db.delete(user_org)
        self.db.commit()
        return True

    def set_primary_organization(
        self,
        user_id: str,
        organization_id: str
    ) -> UserOrganization:
        """
        Set an organization as the user's primary organization.

        Args:
            user_id: User ID
            organization_id: Organization ID

        Returns:
            Updated UserOrganization instance

        Raises:
            ValueError: If user doesn't belong to organization
        """
        # Verify user belongs to this organization
        user_org = self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        ).first()

        if not user_org:
            raise ValueError(
                f"User '{user_id}' doesn't belong to organization '{organization_id}'"
            )

        # Unset current primary
        self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.is_primary == True
        ).update({"is_primary": False})

        # Set new primary
        user_org.is_primary = True
        self.db.commit()
        self.db.refresh(user_org)

        return user_org

    def get_user_organizations(self, user_id: str) -> List[UserOrganization]:
        """
        Get all organizations a user belongs to.

        Args:
            user_id: User ID

        Returns:
            List of UserOrganization instances with organization details
        """
        return self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id
        ).all()

    def get_primary_organization(self, user_id: str) -> Optional[UserOrganization]:
        """
        Get the user's primary organization.

        Args:
            user_id: User ID

        Returns:
            UserOrganization instance if primary is set, None otherwise
        """
        return self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.is_primary == True
        ).first()

    def get_organization_users(
        self,
        organization_id: str,
        role: Optional[str] = None
    ) -> List[UserOrganization]:
        """
        Get all users belonging to an organization.

        Args:
            organization_id: Organization ID
            role: Filter by role (optional)

        Returns:
            List of UserOrganization instances with user details
        """
        query = self.db.query(UserOrganization).filter(
            UserOrganization.organization_id == organization_id
        )

        if role:
            query = query.filter(UserOrganization.role == role)

        return query.all()

    def update_user_role(
        self,
        user_id: str,
        organization_id: str,
        new_role: str
    ) -> UserOrganization:
        """
        Update a user's role in an organization.

        Args:
            user_id: User ID
            organization_id: Organization ID
            new_role: New role to assign

        Returns:
            Updated UserOrganization instance

        Raises:
            ValueError: If user doesn't belong to organization
        """
        user_org = self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        ).first()

        if not user_org:
            raise ValueError(
                f"User '{user_id}' doesn't belong to organization '{organization_id}'"
            )

        user_org.role = new_role
        self.db.commit()
        self.db.refresh(user_org)

        return user_org

    def is_user_in_organization(
        self,
        user_id: str,
        organization_id: str
    ) -> bool:
        """
        Check if a user belongs to an organization.

        Args:
            user_id: User ID
            organization_id: Organization ID

        Returns:
            True if user belongs to organization, False otherwise
        """
        return self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        ).first() is not None

    def get_user_role_in_organization(
        self,
        user_id: str,
        organization_id: str
    ) -> Optional[str]:
        """
        Get a user's role in an organization.

        Args:
            user_id: User ID
            organization_id: Organization ID

        Returns:
            User's role if they belong to organization, None otherwise
        """
        user_org = self.db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        ).first()

        return user_org.role if user_org else None
