"""
Permission Template Service.

Handles template application to organizations and permission management
based on templates and roles.
"""

from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.database.models import (
    Organization,
    Permission,
    PermissionTemplate,
    RoleTemplate,
    OrganizationTemplate,
    OrganizationCustomPermission,
    UserOrganization,
    role_template_permissions,
)
from src.templates import (
    ProductType,
    TemplateDefinition,
    get_template_for_product,
    TEMPLATE_REGISTRY,
)


class PermissionTemplateService:
    """
    Service for managing permission templates and their application to organizations.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_template(self, product_type: ProductType) -> Optional[PermissionTemplate]:
        """
        Get a template from DB or create it from code definition.

        Args:
            product_type: The product type to get/create template for

        Returns:
            PermissionTemplate if found/created, None if no code definition exists
        """
        # Check if template exists in DB
        db_template = self.db.query(PermissionTemplate).filter(
            PermissionTemplate.product_type == product_type.value
        ).first()

        if db_template:
            return db_template

        # Get code definition
        code_template = get_template_for_product(product_type)
        if not code_template:
            return None

        # Create from code definition
        return self._create_template_from_definition(code_template)

    def _create_template_from_definition(self, template_def: TemplateDefinition) -> PermissionTemplate:
        """Create a database template from a code definition."""
        # Create template
        db_template = PermissionTemplate(
            name=template_def.name,
            product_type=template_def.product_type.value,
            version=template_def.version,
            description=template_def.description,
            is_active=True,
        )
        self.db.add(db_template)
        self.db.flush()  # Get ID without committing

        # Create roles
        for role_def in template_def.roles:
            db_role = RoleTemplate(
                template_id=db_template.id,
                role_name=role_def.name,
                display_name=role_def.display_name,
                description=role_def.description,
                inherits_from=role_def.inherits_from,
                priority=role_def.priority,
            )
            self.db.add(db_role)
            self.db.flush()

            # Add role permissions
            all_perms = role_def.get_all_permissions(template_def.get_roles_dict())
            for resource, action in all_perms:
                self.db.execute(
                    role_template_permissions.insert().values(
                        id=self._generate_id(),
                        role_template_id=db_role.id,
                        resource=resource,
                        action=action,
                    )
                )

        self.db.commit()
        self.db.refresh(db_template)
        return db_template

    def apply_template_to_organization(
        self,
        organization_id: str,
        product_type: ProductType,
        owner_user_id: str,
    ) -> OrganizationTemplate:
        """
        Apply a permission template to an organization.

        This will:
        1. Get or create the template in DB
        2. Create OrganizationTemplate record
        3. Assign owner role to the specified user

        Args:
            organization_id: The organization to apply template to
            product_type: The product type template to apply
            owner_user_id: The user to assign as owner

        Returns:
            OrganizationTemplate linking org to template

        Raises:
            ValueError: If organization or template not found
        """
        # Verify organization exists
        org = self.db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not org:
            raise ValueError(f"Organization {organization_id} not found")

        # Get or create template
        template = self.get_or_create_template(product_type)
        if not template:
            raise ValueError(f"No template for product type {product_type}")

        # Check if already applied
        existing = self.db.query(OrganizationTemplate).filter(
            and_(
                OrganizationTemplate.organization_id == organization_id,
                OrganizationTemplate.template_id == template.id,
            )
        ).first()

        if existing:
            # Already applied, just ensure owner role is set
            self._assign_owner_role(template.id, organization_id, owner_user_id)
            return existing

        # Create org template link
        org_template = OrganizationTemplate(
            organization_id=organization_id,
            template_id=template.id,
            applied_version=template.version,
        )
        self.db.add(org_template)

        # Assign owner role to the user
        self._assign_owner_role(template.id, organization_id, owner_user_id)

        self.db.commit()
        self.db.refresh(org_template)
        return org_template

    def _assign_owner_role(
        self,
        template_id: str,
        organization_id: str,
        user_id: str,
    ) -> None:
        """Assign the owner role to a user in an organization."""
        # Get owner role for this template
        owner_role = self.db.query(RoleTemplate).filter(
            and_(
                RoleTemplate.template_id == template_id,
                RoleTemplate.role_name == "owner",
            )
        ).first()

        if not owner_role:
            return

        # Update UserOrganization
        user_org = self.db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
            )
        ).first()

        if user_org:
            user_org.role_template_id = owner_role.id
            user_org.role = "owner"
        else:
            # Create UserOrganization if doesn't exist
            user_org = UserOrganization(
                user_id=user_id,
                organization_id=organization_id,
                role="owner",
                role_template_id=owner_role.id,
                is_primary=True,
            )
            self.db.add(user_org)

    def get_organization_template(self, organization_id: str) -> Optional[OrganizationTemplate]:
        """Get the template applied to an organization."""
        return self.db.query(OrganizationTemplate).filter(
            OrganizationTemplate.organization_id == organization_id
        ).first()

    def add_custom_permission(
        self,
        organization_id: str,
        resource: str,
        action: str,
        granted_by: Optional[str] = None,
    ) -> Permission:
        """
        Add a custom permission to an organization (on top of template).

        Args:
            organization_id: The organization to add permission to
            resource: Permission resource
            action: Permission action
            granted_by: User ID who granted this permission

        Returns:
            The created Permission
        """
        # Check if permission already exists
        existing = self.db.query(Permission).filter(
            and_(
                Permission.organization_id == organization_id,
                Permission.resource == resource,
                Permission.action == action,
            )
        ).first()

        if existing:
            # Mark as custom if not already tracked
            custom_record = self.db.query(OrganizationCustomPermission).filter(
                and_(
                    OrganizationCustomPermission.organization_id == organization_id,
                    OrganizationCustomPermission.permission_id == existing.id,
                )
            ).first()

            if not custom_record:
                custom_record = OrganizationCustomPermission(
                    organization_id=organization_id,
                    permission_id=existing.id,
                    source="custom",
                    granted_by=granted_by,
                )
                self.db.add(custom_record)
                self.db.commit()

            return existing

        # Create new permission
        permission = Permission(
            organization_id=organization_id,
            resource=resource,
            action=action,
        )
        self.db.add(permission)
        self.db.flush()

        # Track as custom
        custom_record = OrganizationCustomPermission(
            organization_id=organization_id,
            permission_id=permission.id,
            source="custom",
            granted_by=granted_by,
        )
        self.db.add(custom_record)
        self.db.commit()

        return permission

    def list_permissions_by_source(
        self,
        organization_id: str,
    ) -> Dict[str, List[Dict]]:
        """
        List all permissions for an org grouped by source.

        Returns:
            Dict with 'template' and 'custom' keys containing permission lists
        """
        # Get all custom permissions with their sources
        custom_records = self.db.query(OrganizationCustomPermission).filter(
            OrganizationCustomPermission.organization_id == organization_id
        ).all()

        custom_perm_ids = {cr.permission_id for cr in custom_records}
        template_perm_ids = set()

        # Get template permissions
        org_template = self.get_organization_template(organization_id)
        if org_template:
            for role in org_template.template.roles:
                result = self.db.execute(
                    role_template_permissions.select().where(
                        role_template_permissions.c.role_template_id == role.id
                    )
                )
                for row in result.fetchall():
                    template_perm_ids.add((row.resource, row.action))

        # Get all org permissions
        all_perms = self.db.query(Permission).filter(
            Permission.organization_id == organization_id
        ).all()

        template_perms = []
        custom_perms = []

        for perm in all_perms:
            perm_dict = {
                "id": perm.id,
                "resource": perm.resource,
                "action": perm.action,
            }
            if perm.id in custom_perm_ids:
                custom_perms.append(perm_dict)
            elif (perm.resource, perm.action) in template_perm_ids:
                perm_dict["source"] = "template"
                template_perms.append(perm_dict)
            else:
                custom_perms.append(perm_dict)

        return {
            "template": template_perms,
            "custom": custom_perms,
        }

    def _generate_id(self) -> str:
        """Generate a UUID string."""
        import uuid
        return str(uuid.uuid4())
