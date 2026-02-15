"""
Role and template definitions for the permission template system.

This module contains:
- ProductType enum: Defines the product types that can have templates
- RoleDefinition: Dataclass for defining a role within a template
- TemplateDefinition: Dataclass for defining a complete permission template
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set, Tuple

# Type alias for permission tuple (resource, action)
Permission = Tuple[str, str]


class ProductType(str, Enum):
    """
    Product types that can have permission templates.

    These match the product types used for billing/provisioning.
    """

    INKPASS_SOLO = "inkpass_solo"
    TENTACKL_SOLO = "tentackl_solo"
    MIMIC_SOLO = "mimic_solo"
    AIOS_BUNDLE = "aios_bundle"


@dataclass
class RoleDefinition:
    """
    Defines a role within a permission template.

    Attributes:
        name: Internal role name (e.g., "owner", "admin", "developer", "viewer")
        display_name: Human-readable role name (e.g., "Owner", "Administrator")
        permissions: Set of (resource, action) tuples for this role
        priority: Higher priority = more permissions (owner=100, admin=80, etc.)
        inherits_from: Name of role to inherit permissions from (optional)
        description: Human-readable description of the role

    Example:
        RoleDefinition(
            name="developer",
            display_name="Developer",
            permissions={("workflows", "view"), ("workflows", "create")},
            priority=50,
            inherits_from="viewer",
        )
    """

    name: str
    display_name: str
    permissions: Set[Permission]
    priority: int = 0
    inherits_from: Optional[str] = None
    description: Optional[str] = None

    def get_all_permissions(self, all_roles: dict) -> Set[Permission]:
        """
        Get all permissions including inherited ones.

        Args:
            all_roles: Dict mapping role names to RoleDefinition objects

        Returns:
            Set of all permissions for this role (including inherited)
        """
        perms = set(self.permissions)

        if self.inherits_from and self.inherits_from in all_roles:
            parent_role = all_roles[self.inherits_from]
            perms |= parent_role.get_all_permissions(all_roles)

        return perms


@dataclass
class TemplateDefinition:
    """
    Defines a complete permission template for a product type.

    Templates are defined in code and synced to the database via admin API.
    Each template contains a set of roles that users can be assigned.

    Attributes:
        name: Unique template name (e.g., "TENTACKL_SOLO")
        product_type: The product type this template applies to
        version: Template version (increment when permissions change)
        roles: List of role definitions within this template
        description: Human-readable description

    Example:
        TemplateDefinition(
            name="TENTACKL_SOLO",
            product_type=ProductType.TENTACKL_SOLO,
            version=1,
            roles=[
                RoleDefinition(name="owner", ...),
                RoleDefinition(name="admin", ...),
                RoleDefinition(name="developer", ...),
                RoleDefinition(name="viewer", ...),
            ],
        )
    """

    name: str
    product_type: ProductType
    version: int
    roles: list = field(default_factory=list)
    description: Optional[str] = None

    def get_role(self, role_name: str) -> Optional[RoleDefinition]:
        """Get a role by name."""
        for role in self.roles:
            if role.name == role_name:
                return role
        return None

    def get_roles_dict(self) -> dict:
        """Get roles as a dict keyed by name."""
        return {role.name: role for role in self.roles}

    def get_role_permissions(self, role_name: str, include_inherited: bool = True) -> Set[Permission]:
        """
        Get all permissions for a role.

        Args:
            role_name: Name of the role
            include_inherited: Whether to include inherited permissions

        Returns:
            Set of (resource, action) tuples
        """
        role = self.get_role(role_name)
        if not role:
            return set()

        if include_inherited:
            return role.get_all_permissions(self.get_roles_dict())
        return set(role.permissions)

    def get_all_permissions(self) -> Set[Permission]:
        """Get all unique permissions across all roles."""
        all_perms = set()
        for role in self.roles:
            all_perms |= role.get_all_permissions(self.get_roles_dict())
        return all_perms
