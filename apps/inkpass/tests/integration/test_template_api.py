"""Integration tests for template API endpoints."""

import pytest
import uuid
from fastapi.testclient import TestClient
from src.database.models import User, Organization, UserOrganization, PermissionTemplate
from src.services.permission_template_service import PermissionTemplateService
from src.services.admin_template_sync_service import AdminTemplateSyncService
from src.templates import ProductType


class TestTemplateAPI:
    """Integration tests for /api/v1/templates endpoints."""

    @pytest.fixture
    def user_with_template(self, client, db):
        """Create a user with template applied and return auth token."""
        unique_email = f"template-test-{uuid.uuid4().hex[:8]}@example.com"

        # Register user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "TestPassword123!",
                "organization_name": f"Template Test Org {uuid.uuid4().hex[:6]}",
            },
        )
        assert response.status_code == 201
        data = response.json()
        user_id = data["user_id"]
        org_id = data["organization_id"]

        # Activate user
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.status = "active"
            db.commit()

        # Sync templates and apply to org
        sync_service = AdminTemplateSyncService(db)
        sync_service.sync_templates_from_code()
        db.commit()

        template_service = PermissionTemplateService(db)
        template_service.apply_template_to_organization(
            organization_id=org_id,
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=user_id,
        )
        db.commit()

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "TestPassword123!"},
        )
        assert login_response.status_code == 200

        return {
            "token": login_response.json()["access_token"],
            "user_id": user_id,
            "org_id": org_id,
        }

    def test_list_templates(self, client, user_with_template):
        """GET /templates returns available templates."""
        response = client.get(
            "/api/v1/templates",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        templates = response.json()
        assert len(templates) > 0
        assert all("id" in t and "name" in t for t in templates)

    def test_list_templates_requires_auth(self, client):
        """GET /templates requires authentication."""
        response = client.get("/api/v1/templates")

        assert response.status_code == 401

    def test_get_template_detail(self, client, db, user_with_template):
        """GET /templates/{id} returns template with roles."""
        # Get a template ID
        template = db.query(PermissionTemplate).first()
        assert template is not None

        response = client.get(
            f"/api/v1/templates/{template.id}",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == template.id
        assert "roles" in data
        assert len(data["roles"]) > 0

    def test_get_template_not_found(self, client, user_with_template):
        """GET /templates/{id} returns 404 for non-existent template."""
        response = client.get(
            "/api/v1/templates/non-existent-id",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 404

    def test_get_template_roles(self, client, db, user_with_template):
        """GET /templates/{id}/roles returns roles for template."""
        template = db.query(PermissionTemplate).first()
        assert template is not None

        response = client.get(
            f"/api/v1/templates/{template.id}/roles",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        roles = response.json()
        assert len(roles) > 0
        role_names = [r["role_name"] for r in roles]
        assert "owner" in role_names

    def test_get_role_permissions(self, client, db, user_with_template):
        """GET /templates/{id}/roles/{role}/permissions returns permissions."""
        template = db.query(PermissionTemplate).first()
        assert template is not None

        response = client.get(
            f"/api/v1/templates/{template.id}/roles/owner/permissions",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        permissions = response.json()
        assert len(permissions) > 0
        assert all("resource" in p and "action" in p for p in permissions)

    def test_get_organization_current_template(self, client, user_with_template):
        """GET /templates/organization/current returns org's template."""
        response = client.get(
            "/api/v1/templates/organization/current",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == user_with_template["org_id"]
        assert "template_id" in data
        assert "applied_version" in data


class TestRoleAPI:
    """Integration tests for /api/v1/roles endpoints."""

    @pytest.fixture
    def user_with_template(self, client, db):
        """Create a user with template applied and return auth token."""
        unique_email = f"role-test-{uuid.uuid4().hex[:8]}@example.com"

        # Register user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "TestPassword123!",
                "organization_name": f"Role Test Org {uuid.uuid4().hex[:6]}",
            },
        )
        assert response.status_code == 201
        data = response.json()
        user_id = data["user_id"]
        org_id = data["organization_id"]

        # Activate user
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.status = "active"
            db.commit()

        # Sync templates and apply to org
        sync_service = AdminTemplateSyncService(db)
        sync_service.sync_templates_from_code()
        db.commit()

        template_service = PermissionTemplateService(db)
        template_service.apply_template_to_organization(
            organization_id=org_id,
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=user_id,
        )
        db.commit()

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "TestPassword123!"},
        )
        assert login_response.status_code == 200

        return {
            "token": login_response.json()["access_token"],
            "user_id": user_id,
            "org_id": org_id,
        }

    def test_list_available_roles(self, client, user_with_template):
        """GET /roles returns available roles for org."""
        response = client.get(
            "/api/v1/roles",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        roles = response.json()
        assert len(roles) >= 4
        role_names = [r["role_name"] for r in roles]
        assert "owner" in role_names
        assert "developer" in role_names

    def test_get_my_role(self, client, user_with_template):
        """GET /roles/users/me returns current user's role."""
        response = client.get(
            "/api/v1/roles/users/me",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_with_template["user_id"]
        assert data["role"] is not None
        assert data["role"]["role_name"] == "owner"

    def test_get_my_permissions(self, client, user_with_template):
        """GET /roles/users/me/permissions returns current user's permissions."""
        response = client.get(
            "/api/v1/roles/users/me/permissions",
            headers={"Authorization": f"Bearer {user_with_template['token']}"},
        )

        assert response.status_code == 200
        permissions = response.json()
        assert len(permissions) > 0
        assert all("resource" in p and "action" in p for p in permissions)


class TestAdminTemplateAPI:
    """Integration tests for /api/v1/admin/templates endpoints."""

    @pytest.fixture
    def admin_user(self, client, db):
        """Create an admin user with permissions:manage permission."""
        unique_email = f"admin-test-{uuid.uuid4().hex[:8]}@example.com"

        # Register user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "TestPassword123!",
                "organization_name": f"Admin Test Org {uuid.uuid4().hex[:6]}",
            },
        )
        assert response.status_code == 201
        data = response.json()
        user_id = data["user_id"]
        org_id = data["organization_id"]

        # Activate user
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.status = "active"
            db.commit()

        # Sync templates and apply to org (makes user owner with all perms)
        sync_service = AdminTemplateSyncService(db)
        sync_service.sync_templates_from_code()
        db.commit()

        template_service = PermissionTemplateService(db)
        template_service.apply_template_to_organization(
            organization_id=org_id,
            product_type=ProductType.AIOS_BUNDLE,
            owner_user_id=user_id,
        )
        db.commit()

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "TestPassword123!"},
        )
        assert login_response.status_code == 200

        return {
            "token": login_response.json()["access_token"],
            "user_id": user_id,
            "org_id": org_id,
        }

    def test_get_sync_status(self, client, admin_user):
        """GET /admin/templates/status returns sync status."""
        response = client.get(
            "/api/v1/admin/templates/status",
            headers={"Authorization": f"Bearer {admin_user['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "needs_sync" in data

    def test_sync_templates(self, client, admin_user):
        """POST /admin/templates/sync syncs templates from code."""
        response = client.post(
            "/api/v1/admin/templates/sync",
            headers={"Authorization": f"Bearer {admin_user['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "created" in data
        assert "updated" in data
        assert "unchanged" in data
        assert "errors" in data

    def test_migrate_orgs_dry_run(self, client, admin_user):
        """POST /admin/templates/migrate-orgs with dry_run=true previews changes."""
        response = client.post(
            "/api/v1/admin/templates/migrate-orgs?dry_run=true",
            headers={"Authorization": f"Bearer {admin_user['token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert "orgs_migrated" in data
        assert "details" in data


class TestPermissionCheckWithRoles:
    """Integration tests for permission checks using role templates."""

    @pytest.fixture
    def org_with_users(self, client, db):
        """Create an org with owner and member users."""
        from src.services.role_service import RoleService

        # Create owner
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": owner_email,
                "password": "TestPassword123!",
                "organization_name": f"Perm Test Org {uuid.uuid4().hex[:6]}",
            },
        )
        assert response.status_code == 201
        data = response.json()
        owner_id = data["user_id"]
        org_id = data["organization_id"]

        # Activate owner
        owner = db.query(User).filter(User.id == owner_id).first()
        owner.status = "active"
        db.commit()

        # Apply template
        sync_service = AdminTemplateSyncService(db)
        sync_service.sync_templates_from_code()
        db.commit()

        template_service = PermissionTemplateService(db)
        template_service.apply_template_to_organization(
            organization_id=org_id,
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=owner_id,
        )
        db.commit()

        # Create member user (will be assigned different roles)
        member_email = f"member-{uuid.uuid4().hex[:8]}@example.com"
        member = User(
            id=str(uuid.uuid4()),
            email=member_email,
            password_hash="test_hash",
            organization_id=org_id,
            status="active",
        )
        db.add(member)

        member_org = UserOrganization(
            id=str(uuid.uuid4()),
            user_id=member.id,
            organization_id=org_id,
            role="member",
            is_primary=True,
        )
        db.add(member_org)
        db.commit()

        # Get owner token
        owner_login = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": "TestPassword123!"},
        )
        assert owner_login.status_code == 200

        return {
            "org_id": org_id,
            "owner_id": owner_id,
            "owner_token": owner_login.json()["access_token"],
            "member_id": member.id,
            "member_email": member_email,
        }

    def test_owner_has_all_permissions(self, client, db, org_with_users):
        """Owner role grants all template permissions."""
        from src.services.role_service import RoleService

        role_service = RoleService(db)
        permissions = role_service.get_user_permissions(
            org_with_users["owner_id"],
            org_with_users["org_id"],
        )

        # Owner should have many permissions
        assert len(permissions) > 30

        # Check critical permissions
        perm_set = {(p["resource"], p["action"]) for p in permissions}
        assert ("workflows", "create") in perm_set
        assert ("workflows", "delete") in perm_set
        assert ("permissions", "manage") in perm_set

    def test_viewer_denied_write_permissions(self, client, db, org_with_users):
        """Viewer role denies write/delete permissions."""
        from src.services.role_service import RoleService

        role_service = RoleService(db)

        # Assign viewer role to member
        role_service.assign_role_to_user(
            user_id=org_with_users["member_id"],
            organization_id=org_with_users["org_id"],
            role_name="viewer",
        )
        db.commit()

        # Viewer should NOT have create/delete permissions
        has_create = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "create",
        )
        has_delete = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "delete",
        )

        assert has_create is False
        assert has_delete is False

        # But viewer should have read permissions
        has_view = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "view",
        )
        assert has_view is True

    def test_developer_can_create_not_delete(self, client, db, org_with_users):
        """Developer can create but not delete."""
        from src.services.role_service import RoleService

        role_service = RoleService(db)

        # Assign developer role to member
        role_service.assign_role_to_user(
            user_id=org_with_users["member_id"],
            organization_id=org_with_users["org_id"],
            role_name="developer",
        )
        db.commit()

        # Developer should have create permission
        has_create = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "create",
        )
        assert has_create is True

        # Developer should NOT have delete permission
        has_delete = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "delete",
        )
        assert has_delete is False

        # Developer should have view permissions (inherited from viewer)
        has_view = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "view",
        )
        assert has_view is True

    def test_role_assignment_via_api(self, client, db, org_with_users):
        """PUT /roles/users/{id} assigns role correctly."""
        # Assign developer role via API
        response = client.put(
            f"/api/v1/roles/users/{org_with_users['member_id']}",
            json={"role": "developer"},
            headers={"Authorization": f"Bearer {org_with_users['owner_token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"]["role_name"] == "developer"

        # Verify permissions updated
        from src.services.role_service import RoleService
        role_service = RoleService(db)

        has_create = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "create",
        )
        assert has_create is True

    def test_admin_has_more_than_developer(self, client, db, org_with_users):
        """Admin role has more permissions than developer."""
        from src.services.role_service import RoleService

        role_service = RoleService(db)

        # Assign admin role
        role_service.assign_role_to_user(
            user_id=org_with_users["member_id"],
            organization_id=org_with_users["org_id"],
            role_name="admin",
        )
        db.commit()

        # Admin should have delete permission (developer doesn't)
        has_delete = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "workflows",
            "delete",
        )
        assert has_delete is True

        # Admin should have manage permissions
        has_manage = role_service.check_user_has_permission(
            org_with_users["member_id"],
            org_with_users["org_id"],
            "users",
            "manage",
        )
        assert has_manage is True
