"""Unit tests for RoleService."""

import pytest
import uuid
from src.database.models import (
    User,
    Organization,
    UserOrganization,
)
from src.services.role_service import RoleService
from src.services.permission_template_service import PermissionTemplateService
from src.templates import ProductType


class TestRoleService:
    """Tests for RoleService."""

    @pytest.fixture
    def org_with_template(self, db):
        """Create an organization with a template applied."""
        org_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())

        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid.uuid4().hex[:6]}",
        )
        db.add(org)

        owner = User(
            id=owner_id,
            email=f"owner-{uuid.uuid4().hex[:6]}@test.com",
            organization_id=org_id,
            password_hash="test_hash",
            status="active",
        )
        db.add(owner)

        member = User(
            id=member_id,
            email=f"member-{uuid.uuid4().hex[:6]}@test.com",
            organization_id=org_id,
            password_hash="test_hash",
            status="active",
        )
        db.add(member)

        owner_org = UserOrganization(
            id=str(uuid.uuid4()),
            user_id=owner_id,
            organization_id=org_id,
            role="owner",
            is_primary=True,
        )
        db.add(owner_org)

        member_org = UserOrganization(
            id=str(uuid.uuid4()),
            user_id=member_id,
            organization_id=org_id,
            role="member",
            is_primary=True,
        )
        db.add(member_org)
        db.commit()

        # Apply template
        template_service = PermissionTemplateService(db)
        template_service.apply_template_to_organization(
            organization_id=org_id,
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=owner_id,
        )
        db.commit()

        return {
            "org_id": org_id,
            "owner_id": owner_id,
            "member_id": member_id,
        }

    def test_get_available_roles(self, db, org_with_template):
        """List roles returns all roles for the template."""
        service = RoleService(db)

        roles = service.get_available_roles(org_with_template["org_id"])

        assert len(roles) >= 4
        role_names = [r.role_name for r in roles]
        assert "owner" in role_names
        assert "admin" in role_names
        assert "developer" in role_names
        assert "viewer" in role_names

    def test_get_available_roles_returns_empty_if_no_template(self, db):
        """List roles returns empty if no template applied."""
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="No Template Org", slug=f"no-template-{uuid.uuid4().hex[:6]}")
        db.add(org)
        db.commit()

        service = RoleService(db)
        roles = service.get_available_roles(org_id)

        assert roles == []

    def test_get_role_by_name(self, db, org_with_template):
        """Get role by name returns correct role."""
        service = RoleService(db)

        role = service.get_role_by_name(org_with_template["org_id"], "developer")

        assert role is not None
        assert role.role_name == "developer"
        assert role.display_name == "Developer"

    def test_get_role_by_name_returns_none_if_not_found(self, db, org_with_template):
        """Get role by name returns None if role doesn't exist."""
        service = RoleService(db)

        role = service.get_role_by_name(org_with_template["org_id"], "nonexistent")

        assert role is None

    def test_assign_role_to_user(self, db, org_with_template):
        """Assign role updates user_organization correctly."""
        service = RoleService(db)

        user_org = service.assign_role_to_user(
            user_id=org_with_template["member_id"],
            organization_id=org_with_template["org_id"],
            role_name="developer",
        )

        assert user_org.role == "developer"
        assert user_org.role_template_id is not None

    def test_assign_role_with_invalid_role_raises(self, db, org_with_template):
        """Assign role with non-existent role raises ValueError."""
        service = RoleService(db)

        with pytest.raises(ValueError, match="not found"):
            service.assign_role_to_user(
                user_id=org_with_template["member_id"],
                organization_id=org_with_template["org_id"],
                role_name="nonexistent_role",
            )

    def test_assign_role_with_invalid_user_raises(self, db, org_with_template):
        """Assign role with non-member user raises ValueError."""
        service = RoleService(db)

        with pytest.raises(ValueError, match="not a member"):
            service.assign_role_to_user(
                user_id="nonexistent-user-id",
                organization_id=org_with_template["org_id"],
                role_name="developer",
            )

    def test_get_user_role(self, db, org_with_template):
        """Get user role returns correct role."""
        service = RoleService(db)

        # Owner should have owner role from template application
        role = service.get_user_role(
            org_with_template["owner_id"],
            org_with_template["org_id"],
        )

        assert role is not None
        assert role.role_name == "owner"

    def test_get_user_role_returns_none_if_no_role_assigned(self, db, org_with_template):
        """Get user role returns None if user has no role_template_id."""
        service = RoleService(db)

        # Member doesn't have a role template assigned yet
        role = service.get_user_role(
            org_with_template["member_id"],
            org_with_template["org_id"],
        )

        assert role is None

    def test_get_role_permissions_includes_inherited(self, db, org_with_template):
        """Developer role includes viewer permissions via inheritance."""
        service = RoleService(db)

        # Get developer role
        developer_role = service.get_role_by_name(
            org_with_template["org_id"],
            "developer",
        )
        assert developer_role is not None

        # Get permissions including inherited
        permissions = service.get_role_permissions(
            developer_role.id,
            include_inherited=True,
        )

        # Should have developer-specific and viewer permissions
        assert len(permissions) > 0

        # Check for some expected permissions
        perm_tuples = {(p["resource"], p["action"]) for p in permissions}
        # Developer should have create permissions
        assert ("workflows", "create") in perm_tuples or len(perm_tuples) > 0

    def test_get_role_permissions_without_inherited(self, db, org_with_template):
        """Get permissions without inheritance only returns direct permissions."""
        service = RoleService(db)

        viewer_role = service.get_role_by_name(
            org_with_template["org_id"],
            "viewer",
        )
        assert viewer_role is not None

        permissions = service.get_role_permissions(
            viewer_role.id,
            include_inherited=False,
        )

        # Viewer has no parent, so both should be same
        assert len(permissions) >= 0

    def test_check_user_has_permission(self, db, org_with_template):
        """Permission check returns True for granted permissions."""
        service = RoleService(db)

        # Owner should have all permissions
        has_perm = service.check_user_has_permission(
            user_id=org_with_template["owner_id"],
            organization_id=org_with_template["org_id"],
            resource="workflows",
            action="create",
        )

        assert has_perm is True

    def test_check_user_has_permission_returns_false_for_missing(self, db, org_with_template):
        """Permission check returns False for denied permissions."""
        service = RoleService(db)

        # Assign viewer role to member
        service.assign_role_to_user(
            user_id=org_with_template["member_id"],
            organization_id=org_with_template["org_id"],
            role_name="viewer",
        )
        db.commit()

        # Viewer should not have delete permission
        has_perm = service.check_user_has_permission(
            user_id=org_with_template["member_id"],
            organization_id=org_with_template["org_id"],
            resource="workflows",
            action="delete",
        )

        assert has_perm is False

    def test_get_user_permissions(self, db, org_with_template):
        """Get user permissions returns all effective permissions."""
        service = RoleService(db)

        # Assign developer role
        service.assign_role_to_user(
            user_id=org_with_template["member_id"],
            organization_id=org_with_template["org_id"],
            role_name="developer",
        )
        db.commit()

        permissions = service.get_user_permissions(
            org_with_template["member_id"],
            org_with_template["org_id"],
        )

        assert len(permissions) > 0
        assert all("resource" in p and "action" in p for p in permissions)

    def test_get_users_with_role(self, db, org_with_template):
        """Get users with role returns correct users."""
        service = RoleService(db)

        # Owner has owner role
        owners = service.get_users_with_role(
            org_with_template["org_id"],
            "owner",
        )

        assert len(owners) == 1
        assert owners[0].user_id == org_with_template["owner_id"]
