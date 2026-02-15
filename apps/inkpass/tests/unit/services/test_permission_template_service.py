"""Unit tests for PermissionTemplateService."""

import pytest
import uuid
from src.database.models import (
    User,
    Organization,
    UserOrganization,
    PermissionTemplate,
    RoleTemplate,
    OrganizationTemplate,
    role_template_permissions,
)
from src.services.permission_template_service import PermissionTemplateService
from src.services.role_service import RoleService
from src.templates import ProductType, TEMPLATE_REGISTRY


class TestPermissionTemplateService:
    """Tests for PermissionTemplateService."""

    @pytest.fixture
    def org_with_owner(self, db):
        """Create an organization with an owner user."""
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid.uuid4().hex[:6]}",
        )
        db.add(org)

        user = User(
            id=user_id,
            email=f"owner-{uuid.uuid4().hex[:6]}@test.com",
            organization_id=org_id,
            password_hash="test_hash",
            status="active",
        )
        db.add(user)

        user_org = UserOrganization(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=org_id,
            role="owner",
            is_primary=True,
        )
        db.add(user_org)
        db.commit()

        return {"org_id": org_id, "user_id": user_id}

    def test_get_or_create_template_creates_new(self, db):
        """Template is created if it doesn't exist."""
        service = PermissionTemplateService(db)

        # Clear any existing template for this product type (delete in order due to FK constraints)
        template = db.query(PermissionTemplate).filter(
            PermissionTemplate.product_type == ProductType.TENTACKL_SOLO.value
        ).first()
        if template:
            role_ids = [r.id for r in db.query(RoleTemplate.id).filter(RoleTemplate.template_id == template.id).all()]
            if role_ids:
                db.execute(role_template_permissions.delete().where(
                    role_template_permissions.c.role_template_id.in_(role_ids)
                ))
            db.query(OrganizationTemplate).filter(OrganizationTemplate.template_id == template.id).delete()
            db.query(RoleTemplate).filter(RoleTemplate.template_id == template.id).delete()
            db.query(PermissionTemplate).filter(PermissionTemplate.id == template.id).delete()
            db.commit()

        # Get or create should create
        template = service.get_or_create_template(ProductType.TENTACKL_SOLO)

        assert template is not None
        assert template.product_type == ProductType.TENTACKL_SOLO.value
        assert template.version >= 1
        assert template.is_active is True

    def test_get_or_create_template_returns_existing(self, db):
        """Existing template is returned without modification."""
        service = PermissionTemplateService(db)

        # Create template first
        template1 = service.get_or_create_template(ProductType.TENTACKL_SOLO)
        template_id = template1.id
        db.commit()

        # Get again - should return same template
        template2 = service.get_or_create_template(ProductType.TENTACKL_SOLO)

        assert template2.id == template_id

    def test_apply_template_creates_org_template(self, db, org_with_owner):
        """Template application creates OrganizationTemplate record."""
        service = PermissionTemplateService(db)

        org_template = service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )

        assert org_template is not None
        assert org_template.organization_id == org_with_owner["org_id"]
        assert org_template.applied_version >= 1

    def test_apply_template_assigns_owner_role(self, db, org_with_owner):
        """Owner gets owner role when template is applied."""
        service = PermissionTemplateService(db)

        service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Check user_org has role_template_id set
        user_org = db.query(UserOrganization).filter(
            UserOrganization.user_id == org_with_owner["user_id"],
            UserOrganization.organization_id == org_with_owner["org_id"],
        ).first()

        assert user_org is not None
        assert user_org.role_template_id is not None
        assert user_org.role == "owner"

    def test_apply_template_creates_role_templates(self, db, org_with_owner):
        """All role templates (owner, admin, developer, viewer) are created."""
        service = PermissionTemplateService(db)

        org_template = service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Check roles were created
        roles = db.query(RoleTemplate).filter(
            RoleTemplate.template_id == org_template.template_id
        ).all()

        role_names = {r.role_name for r in roles}
        assert "owner" in role_names
        assert "admin" in role_names
        assert "developer" in role_names
        assert "viewer" in role_names

    def test_get_organization_template(self, db, org_with_owner):
        """Get organization template returns correct record."""
        service = PermissionTemplateService(db)

        # Apply template
        service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Get template
        org_template = service.get_organization_template(org_with_owner["org_id"])

        assert org_template is not None
        assert org_template.organization_id == org_with_owner["org_id"]

    def test_get_organization_template_returns_none_if_not_applied(self, db, org_with_owner):
        """Get organization template returns None if no template applied."""
        service = PermissionTemplateService(db)

        org_template = service.get_organization_template(org_with_owner["org_id"])

        assert org_template is None

    def test_apply_template_twice_is_idempotent(self, db, org_with_owner):
        """Applying template twice doesn't create duplicate."""
        service = PermissionTemplateService(db)

        org_template1 = service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        org_template2 = service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )

        assert org_template1.id == org_template2.id

    def test_apply_template_with_invalid_org_raises(self, db, org_with_owner):
        """Applying template to non-existent org raises ValueError."""
        service = PermissionTemplateService(db)

        with pytest.raises(ValueError, match="not found"):
            service.apply_template_to_organization(
                organization_id="non-existent-org-id",
                product_type=ProductType.TENTACKL_SOLO,
                owner_user_id=org_with_owner["user_id"],
            )

    def test_owner_gets_all_permissions_on_product_assignment(self, db, org_with_owner):
        """Owner gets ALL permissions defined in template when product is assigned."""
        template_service = PermissionTemplateService(db)
        role_service = RoleService(db)

        # Apply AIOS_BUNDLE template (has the most permissions)
        template_service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.AIOS_BUNDLE,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Get owner's permissions
        permissions = role_service.get_user_permissions(
            org_with_owner["user_id"],
            org_with_owner["org_id"],
        )

        # Owner should have many permissions (AIOS_BUNDLE has 121)
        assert len(permissions) > 50, f"Expected many permissions, got {len(permissions)}"

        # Convert to set of tuples for easy checking
        perm_set = {(p["resource"], p["action"]) for p in permissions}

        # Check key permissions are present
        assert ("workflows", "create") in perm_set, "Owner should have workflows:create"
        assert ("workflows", "delete") in perm_set, "Owner should have workflows:delete"
        assert ("billing", "manage") in perm_set, "Owner should have billing:manage"
        assert ("permissions", "manage") in perm_set, "Owner should have permissions:manage"
        assert ("organization", "manage") in perm_set, "Owner should have organization:manage"

    def test_aios_bundle_owner_has_all_service_permissions(self, db, org_with_owner):
        """AIOS_BUNDLE owner has permissions for all services."""
        template_service = PermissionTemplateService(db)
        role_service = RoleService(db)

        template_service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.AIOS_BUNDLE,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        permissions = role_service.get_user_permissions(
            org_with_owner["user_id"],
            org_with_owner["org_id"],
        )
        perm_set = {(p["resource"], p["action"]) for p in permissions}

        # Should have permissions for Tentackl resources
        assert ("workflows", "create") in perm_set
        assert ("agents", "execute") in perm_set
        assert ("plans", "create") in perm_set

        # Should have permissions for Mimic resources
        assert ("notifications", "send") in perm_set
        assert ("templates", "create") in perm_set

        # Should have permissions for InkPass resources
        assert ("users", "create") in perm_set
        assert ("api_keys", "create") in perm_set

    def test_permission_count_matches_template_definition(self, db, org_with_owner):
        """Permission count matches what's defined in the template."""
        template_service = PermissionTemplateService(db)
        role_service = RoleService(db)

        template_service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Get owner permissions
        permissions = role_service.get_user_permissions(
            org_with_owner["user_id"],
            org_with_owner["org_id"],
        )

        # Get expected count from template definition
        template_def = TEMPLATE_REGISTRY[ProductType.TENTACKL_SOLO]
        owner_role_def = next(r for r in template_def.roles if r.name == "owner")
        expected_count = len(owner_role_def.permissions)

        assert len(permissions) == expected_count, (
            f"Expected {expected_count} permissions from template, got {len(permissions)}"
        )

    def test_viewer_has_fewer_permissions_than_owner(self, db, org_with_owner):
        """Viewer role has significantly fewer permissions than owner."""
        template_service = PermissionTemplateService(db)
        role_service = RoleService(db)

        template_service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Get viewer role
        viewer_role = role_service.get_role_by_name(org_with_owner["org_id"], "viewer")
        assert viewer_role is not None

        # Get permissions for viewer (without inheritance since viewer is base)
        viewer_perms = role_service.get_role_permissions(viewer_role.id, include_inherited=False)

        # Get owner permissions
        owner_perms = role_service.get_user_permissions(
            org_with_owner["user_id"],
            org_with_owner["org_id"],
        )

        # Viewer should have fewer permissions
        assert len(viewer_perms) < len(owner_perms), (
            f"Viewer ({len(viewer_perms)}) should have fewer permissions than owner ({len(owner_perms)})"
        )

        # Viewer should only have read-like permissions
        viewer_perm_set = {(p["resource"], p["action"]) for p in viewer_perms}
        for resource, action in viewer_perm_set:
            assert action in ("read", "view", "list", "search", "query"), (
                f"Viewer should only have read permissions, found {resource}:{action}"
            )
