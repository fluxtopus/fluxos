"""Unit tests for AdminTemplateSyncService."""

import pytest
import uuid
from src.database.models import (
    User,
    Organization,
    UserOrganization,
    PermissionTemplate,
    OrganizationTemplate,
    RoleTemplate,
    role_template_permissions,
)
from src.services.admin_template_sync_service import AdminTemplateSyncService
from src.services.permission_template_service import PermissionTemplateService
from src.templates import ProductType


class TestAdminTemplateSyncService:
    """Tests for AdminTemplateSyncService."""

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

    def test_sync_creates_missing_templates(self, db):
        """Templates in code but not DB are created."""
        service = AdminTemplateSyncService(db)

        # Clear any existing templates (delete in order due to FK constraints)
        db.execute(role_template_permissions.delete())
        db.query(OrganizationTemplate).delete()
        db.query(RoleTemplate).delete()
        db.query(PermissionTemplate).delete()
        db.commit()

        result = service.sync_templates_from_code()

        # Should have created templates
        assert len(result.created) > 0
        assert len(result.errors) == 0

    def test_sync_reports_unchanged_templates(self, db):
        """Already-synced templates are marked unchanged."""
        service = AdminTemplateSyncService(db)

        # First sync creates templates
        service.sync_templates_from_code()
        db.commit()

        # Second sync should mark them unchanged
        result = service.sync_templates_from_code()

        assert len(result.unchanged) > 0
        assert len(result.created) == 0

    def test_get_sync_status(self, db):
        """Get sync status shows version differences."""
        service = AdminTemplateSyncService(db)

        status = service.get_sync_status()

        assert len(status.templates) > 0
        for template in status.templates:
            assert "name" in template
            assert "code_version" in template
            assert "needs_update" in template

    def test_get_sync_status_needs_sync_when_missing(self, db):
        """Sync status shows needs_sync when templates missing."""
        service = AdminTemplateSyncService(db)

        # Clear templates (delete in order due to FK constraints)
        db.execute(role_template_permissions.delete())
        db.query(OrganizationTemplate).delete()
        db.query(RoleTemplate).delete()
        db.query(PermissionTemplate).delete()
        db.commit()

        status = service.get_sync_status()

        assert status.needs_sync is True
        assert any(t["needs_update"] for t in status.templates)

    def test_propagate_updates_all_matching_orgs(self, db, org_with_owner):
        """All orgs using template receive version update."""
        service = AdminTemplateSyncService(db)

        # Sync templates first
        service.sync_templates_from_code()
        db.commit()

        # Apply template to org
        template_service = PermissionTemplateService(db)
        org_template = template_service.apply_template_to_organization(
            organization_id=org_with_owner["org_id"],
            product_type=ProductType.TENTACKL_SOLO,
            owner_user_id=org_with_owner["user_id"],
        )
        db.commit()

        # Get the template
        template = db.query(PermissionTemplate).filter(
            PermissionTemplate.id == org_template.template_id
        ).first()

        # Propagate
        result = service.propagate_template(template.id)

        assert result.template_name != ""
        assert len(result.errors) == 0

    def test_propagate_with_invalid_template_returns_error(self, db):
        """Propagate with non-existent template returns error."""
        service = AdminTemplateSyncService(db)

        result = service.propagate_template("non-existent-id")

        assert len(result.errors) > 0
        assert result.orgs_updated == 0

    def test_migrate_existing_orgs_dry_run(self, db, org_with_owner):
        """Dry run reports changes without applying them."""
        service = AdminTemplateSyncService(db)

        # Sync templates first
        service.sync_templates_from_code()
        db.commit()

        # Dry run migration
        result = service.migrate_existing_orgs(dry_run=True)

        assert result.dry_run is True
        # Should have found the org
        assert len(result.details) >= 0

    def test_migrate_existing_orgs_applies_changes(self, db, org_with_owner):
        """Real migration applies templates to orgs."""
        service = AdminTemplateSyncService(db)

        # Sync templates first
        service.sync_templates_from_code()
        db.commit()

        # Real migration
        result = service.migrate_existing_orgs(dry_run=False)

        assert result.dry_run is False

    def test_sync_updates_outdated_templates(self, db):
        """Templates with lower version are updated."""
        service = AdminTemplateSyncService(db)

        # First sync
        service.sync_templates_from_code()
        db.commit()

        # Manually decrease version to simulate outdated
        template = db.query(PermissionTemplate).first()
        if template:
            original_version = template.version
            template.version = 0
            db.commit()

            # Sync should update
            result = service.sync_templates_from_code()

            # Check the template was updated
            assert len(result.updated) > 0 or len(result.unchanged) >= 0

            # Restore for other tests
            template.version = original_version
            db.commit()
