"""
Admin Template Sync Service.

Provides admin-only operations for syncing permission templates from code
definitions to the database and propagating changes to organizations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import and_, select

from src.database.models import (
    Organization,
    PermissionTemplate,
    RoleTemplate,
    OrganizationTemplate,
    UserOrganization,
    role_template_permissions,
)
from src.templates import (
    ProductType,
    TemplateDefinition,
    TEMPLATE_REGISTRY,
    get_template_for_product,
)


@dataclass
class SyncResult:
    """Result of template sync operation."""
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class PropagateResult:
    """Result of template propagation."""
    template_name: str = ""
    orgs_updated: int = 0
    permissions_added: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class SyncStatus:
    """Status of template sync."""
    templates: List[Dict] = field(default_factory=list)
    needs_sync: bool = False


@dataclass
class MigrationResult:
    """Result of org migration."""
    orgs_migrated: int = 0
    dry_run: bool = True
    details: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class AdminTemplateSyncService:
    """
    Admin service for syncing permission templates from code to database.

    This service should only be called by administrators through the admin API.
    """

    def __init__(self, db: Session):
        self.db = db

    def sync_templates_from_code(self) -> SyncResult:
        """
        Sync all templates from code definitions to database.

        Compares code TEMPLATE_REGISTRY with DB templates and:
        - Creates templates that don't exist in DB
        - Updates templates that have a newer version in code
        - Leaves unchanged templates alone

        Returns:
            SyncResult with lists of created, updated, unchanged templates
        """
        result = SyncResult()

        for product_type, code_template in TEMPLATE_REGISTRY.items():
            try:
                db_template = self.db.query(PermissionTemplate).filter(
                    PermissionTemplate.name == code_template.name
                ).first()

                if not db_template:
                    # Create new template
                    self._create_template(code_template)
                    result.created.append(code_template.name)
                elif db_template.version < code_template.version:
                    # Update existing template
                    self._update_template(db_template, code_template)
                    result.updated.append(code_template.name)
                else:
                    result.unchanged.append(code_template.name)

            except Exception as e:
                result.errors.append(f"{code_template.name}: {str(e)}")

        self.db.commit()
        return result

    def _create_template(self, template_def: TemplateDefinition) -> PermissionTemplate:
        """Create a new template from code definition."""
        db_template = PermissionTemplate(
            name=template_def.name,
            product_type=template_def.product_type.value,
            version=template_def.version,
            description=template_def.description,
            is_active=True,
        )
        self.db.add(db_template)
        self.db.flush()

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

            # Add permissions
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

        return db_template

    def _update_template(
        self,
        db_template: PermissionTemplate,
        code_template: TemplateDefinition,
    ) -> None:
        """Update an existing template to match code definition."""
        # Update template metadata
        db_template.version = code_template.version
        db_template.description = code_template.description

        # Get existing roles
        existing_roles = {r.role_name: r for r in db_template.roles}

        for role_def in code_template.roles:
            if role_def.name in existing_roles:
                # Update existing role
                db_role = existing_roles[role_def.name]
                db_role.display_name = role_def.display_name
                db_role.description = role_def.description
                db_role.inherits_from = role_def.inherits_from
                db_role.priority = role_def.priority

                # Clear and re-add permissions
                self.db.execute(
                    role_template_permissions.delete().where(
                        role_template_permissions.c.role_template_id == db_role.id
                    )
                )

                all_perms = role_def.get_all_permissions(code_template.get_roles_dict())
                for resource, action in all_perms:
                    self.db.execute(
                        role_template_permissions.insert().values(
                            id=self._generate_id(),
                            role_template_id=db_role.id,
                            resource=resource,
                            action=action,
                        )
                    )
            else:
                # Create new role
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

                all_perms = role_def.get_all_permissions(code_template.get_roles_dict())
                for resource, action in all_perms:
                    self.db.execute(
                        role_template_permissions.insert().values(
                            id=self._generate_id(),
                            role_template_id=db_role.id,
                            resource=resource,
                            action=action,
                        )
                    )

    def propagate_template(self, template_id: str) -> PropagateResult:
        """
        Propagate template changes to all organizations using it.

        This updates the applied_version in organization_templates
        to match the current template version.

        Args:
            template_id: ID of the template to propagate

        Returns:
            PropagateResult with counts of updated orgs
        """
        result = PropagateResult()

        template = self.db.query(PermissionTemplate).filter(
            PermissionTemplate.id == template_id
        ).first()

        if not template:
            result.errors.append(f"Template {template_id} not found")
            return result

        result.template_name = template.name

        # Find orgs with outdated version
        outdated_orgs = self.db.query(OrganizationTemplate).filter(
            and_(
                OrganizationTemplate.template_id == template_id,
                OrganizationTemplate.applied_version < template.version,
            )
        ).all()

        for org_template in outdated_orgs:
            try:
                org_template.applied_version = template.version
                result.orgs_updated += 1
            except Exception as e:
                result.errors.append(
                    f"Org {org_template.organization_id}: {str(e)}"
                )

        self.db.commit()
        return result

    def get_sync_status(self) -> SyncStatus:
        """
        Get the sync status comparing code vs DB templates.

        Returns:
            SyncStatus with version differences
        """
        status = SyncStatus()

        for product_type, code_template in TEMPLATE_REGISTRY.items():
            db_template = self.db.query(PermissionTemplate).filter(
                PermissionTemplate.name == code_template.name
            ).first()

            template_status = {
                "name": code_template.name,
                "product_type": product_type.value,
                "code_version": code_template.version,
                "db_version": db_template.version if db_template else None,
                "exists_in_db": db_template is not None,
                "needs_update": False,
            }

            if not db_template:
                template_status["needs_update"] = True
                status.needs_sync = True
            elif db_template.version < code_template.version:
                template_status["needs_update"] = True
                status.needs_sync = True

            status.templates.append(template_status)

        return status

    def migrate_existing_orgs(self, dry_run: bool = True) -> MigrationResult:
        """
        Migrate existing organizations to the template system.

        This will:
        1. Detect which template each org should have (by settings/product type)
        2. Apply templates to orgs that don't have one
        3. Assign owner roles to existing owners

        Args:
            dry_run: If True, don't make changes, just report what would happen

        Returns:
            MigrationResult with details of what was/would be migrated
        """
        result = MigrationResult(dry_run=dry_run)

        # Get orgs without a template
        orgs_without_template = self.db.query(Organization).filter(
            ~Organization.id.in_(
                select(OrganizationTemplate.organization_id)
            )
        ).all()

        for org in orgs_without_template:
            # Determine product type for this org
            # Default to AIOS_BUNDLE, could be refined based on org settings
            product_type = self._detect_org_product_type(org)

            # Find owner (user with is_primary=True in user_organizations)
            owner_user_org = self.db.query(UserOrganization).filter(
                and_(
                    UserOrganization.organization_id == org.id,
                    UserOrganization.is_primary == True,
                )
            ).first()

            detail = {
                "organization_id": org.id,
                "organization_name": org.name,
                "product_type": product_type.value,
                "owner_user_id": owner_user_org.user_id if owner_user_org else None,
                "action": "would_apply_template" if dry_run else "applied_template",
            }

            if not dry_run and owner_user_org:
                try:
                    # Get or create template
                    template = self._get_or_create_template(product_type)

                    # Apply template
                    org_template = OrganizationTemplate(
                        organization_id=org.id,
                        template_id=template.id,
                        applied_version=template.version,
                    )
                    self.db.add(org_template)

                    # Assign owner role
                    owner_role = self.db.query(RoleTemplate).filter(
                        and_(
                            RoleTemplate.template_id == template.id,
                            RoleTemplate.role_name == "owner",
                        )
                    ).first()

                    if owner_role:
                        owner_user_org.role_template_id = owner_role.id
                        owner_user_org.role = "owner"

                    detail["action"] = "applied_template"
                    result.orgs_migrated += 1

                except Exception as e:
                    detail["action"] = "error"
                    detail["error"] = str(e)
                    result.errors.append(f"{org.id}: {str(e)}")

            result.details.append(detail)

        if not dry_run:
            self.db.commit()

        return result

    def _detect_org_product_type(self, org: Organization) -> ProductType:
        """
        Detect the product type for an organization.

        Could be based on org settings, subscription, etc.
        Defaults to AIOS_BUNDLE.
        """
        # Check org settings for product type hint
        if org.settings and isinstance(org.settings, dict):
            product_hint = org.settings.get("product_type")
            if product_hint:
                try:
                    return ProductType(product_hint)
                except ValueError:
                    pass

        # Default to full bundle
        return ProductType.AIOS_BUNDLE

    def _get_or_create_template(self, product_type: ProductType) -> PermissionTemplate:
        """Get a template from DB or create it."""
        db_template = self.db.query(PermissionTemplate).filter(
            PermissionTemplate.product_type == product_type.value
        ).first()

        if db_template:
            return db_template

        code_template = get_template_for_product(product_type)
        if not code_template:
            raise ValueError(f"No template for {product_type}")

        return self._create_template(code_template)

    def _generate_id(self) -> str:
        """Generate a UUID string."""
        import uuid
        return str(uuid.uuid4())
