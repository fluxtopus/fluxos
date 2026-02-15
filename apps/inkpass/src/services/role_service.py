"""
Role Service.

Handles role assignment and permission checks based on role templates.
"""

from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, select

from src.database.models import (
    RoleTemplate,
    UserOrganization,
    OrganizationTemplate,
    PermissionTemplate,
    role_template_permissions,
)


class RoleService:
    """
    Service for managing user roles and checking permissions via role templates.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_available_roles(self, organization_id: str) -> List[RoleTemplate]:
        """
        Get all roles available for an organization.

        This returns the roles from the template applied to the organization.

        Args:
            organization_id: The organization to get roles for

        Returns:
            List of RoleTemplate objects
        """
        org_template = self.db.query(OrganizationTemplate).filter(
            OrganizationTemplate.organization_id == organization_id
        ).first()

        if not org_template:
            return []

        return self.db.query(RoleTemplate).filter(
            RoleTemplate.template_id == org_template.template_id
        ).order_by(RoleTemplate.priority.desc()).all()

    def get_role_by_name(
        self,
        organization_id: str,
        role_name: str,
    ) -> Optional[RoleTemplate]:
        """
        Get a specific role by name for an organization.

        Args:
            organization_id: The organization
            role_name: Name of the role (e.g., "owner", "developer")

        Returns:
            RoleTemplate if found
        """
        org_template = self.db.query(OrganizationTemplate).filter(
            OrganizationTemplate.organization_id == organization_id
        ).first()

        if not org_template:
            return None

        return self.db.query(RoleTemplate).filter(
            and_(
                RoleTemplate.template_id == org_template.template_id,
                RoleTemplate.role_name == role_name,
            )
        ).first()

    def assign_role_to_user(
        self,
        user_id: str,
        organization_id: str,
        role_name: str,
    ) -> UserOrganization:
        """
        Assign a role to a user in an organization.

        Args:
            user_id: The user to assign role to
            organization_id: The organization
            role_name: Name of the role to assign

        Returns:
            Updated UserOrganization

        Raises:
            ValueError: If role not found or user not in org
        """
        # Get the role
        role = self.get_role_by_name(organization_id, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' not found for organization")

        # Get or create UserOrganization
        user_org = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
            )
        ).first()

        if not user_org:
            raise ValueError(f"User {user_id} is not a member of organization {organization_id}")

        # Update role
        user_org.role = role_name
        user_org.role_template_id = role.id

        self.db.commit()
        self.db.refresh(user_org)
        return user_org

    def get_user_role(
        self,
        user_id: str,
        organization_id: str,
    ) -> Optional[RoleTemplate]:
        """
        Get the role assigned to a user in an organization.

        Args:
            user_id: The user
            organization_id: The organization

        Returns:
            RoleTemplate if user has a role assigned
        """
        user_org = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
            )
        ).first()

        if not user_org or not user_org.role_template_id:
            return None

        return self.db.query(RoleTemplate).filter(
            RoleTemplate.id == user_org.role_template_id
        ).first()

    def get_role_permissions(
        self,
        role_template_id: str,
        include_inherited: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Get all permissions for a role.

        Args:
            role_template_id: The role template ID
            include_inherited: Whether to include inherited permissions

        Returns:
            List of {"resource": str, "action": str} dicts
        """
        role = self.db.query(RoleTemplate).filter(
            RoleTemplate.id == role_template_id
        ).first()

        if not role:
            return []

        permissions = set()

        # Get direct permissions
        result = self.db.execute(
            select(
                role_template_permissions.c.resource,
                role_template_permissions.c.action,
            ).where(
                role_template_permissions.c.role_template_id == role_template_id
            )
        )
        for row in result.fetchall():
            permissions.add((row.resource, row.action))

        # Get inherited permissions
        if include_inherited and role.inherits_from:
            parent_role = self.db.query(RoleTemplate).filter(
                and_(
                    RoleTemplate.template_id == role.template_id,
                    RoleTemplate.role_name == role.inherits_from,
                )
            ).first()

            if parent_role:
                parent_perms = self.get_role_permissions(
                    parent_role.id,
                    include_inherited=True,
                )
                for perm in parent_perms:
                    permissions.add((perm["resource"], perm["action"]))

        return [
            {"resource": r, "action": a}
            for r, a in sorted(permissions)
        ]

    def get_user_permissions(
        self,
        user_id: str,
        organization_id: str,
    ) -> List[Dict[str, str]]:
        """
        Get all effective permissions for a user in an organization.

        This resolves permissions from the user's role template.

        Args:
            user_id: The user
            organization_id: The organization

        Returns:
            List of {"resource": str, "action": str} dicts
        """
        role = self.get_user_role(user_id, organization_id)
        if not role:
            return []

        return self.get_role_permissions(role.id, include_inherited=True)

    def check_user_has_permission(
        self,
        user_id: str,
        organization_id: str,
        resource: str,
        action: str,
    ) -> bool:
        """
        Check if a user has a specific permission via their role.

        This is the lazy evaluation method used by auth middleware.

        Args:
            user_id: The user to check
            organization_id: The organization context
            resource: Permission resource (e.g., "workflows")
            action: Permission action (e.g., "create")

        Returns:
            True if user has permission, False otherwise
        """
        role = self.get_user_role(user_id, organization_id)
        if not role:
            return False

        permissions = self.get_role_permissions(role.id, include_inherited=True)
        return any(
            p["resource"] == resource and p["action"] == action
            for p in permissions
        )

    def get_users_with_role(
        self,
        organization_id: str,
        role_name: str,
    ) -> List[UserOrganization]:
        """
        Get all users with a specific role in an organization.

        Args:
            organization_id: The organization
            role_name: The role name to filter by

        Returns:
            List of UserOrganization records
        """
        role = self.get_role_by_name(organization_id, role_name)
        if not role:
            return []

        return self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.role_template_id == role.id,
            )
        ).all()
