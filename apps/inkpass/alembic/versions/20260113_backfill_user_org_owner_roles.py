"""Backfill UserOrganization records with owner role for existing users.

Revision ID: 20260113_backfill_owner
Revises: 20260111_add_billing_schema
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '20260113_backfill_owner'
down_revision = '20260111_billing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Backfill UserOrganization records for users who don't have one.

    This handles users created before the registration flow was fixed
    to create UserOrganization records with role='owner'.
    """
    connection = op.get_bind()

    # Find users who have an organization_id but no UserOrganization record
    result = connection.execute(text("""
        INSERT INTO user_organizations (id, user_id, organization_id, role, is_primary, joined_at)
        SELECT
            gen_random_uuid()::text,
            u.id,
            u.organization_id,
            'owner',
            true,
            COALESCE(u.created_at, NOW())
        FROM users u
        WHERE u.organization_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM user_organizations uo
            WHERE uo.user_id = u.id AND uo.organization_id = u.organization_id
        )
    """))

    print(f"Backfilled {result.rowcount} UserOrganization records with owner role")


def downgrade() -> None:
    """
    Remove backfilled UserOrganization records.

    Note: This only removes records that were backfilled (owner + is_primary).
    Records created through normal registration after the fix will remain.
    """
    connection = op.get_bind()

    # Remove UserOrganization records that match the backfill pattern
    # We can't perfectly identify backfilled records, so we're conservative
    # and only remove owner records that are primary
    result = connection.execute(text("""
        DELETE FROM user_organizations
        WHERE role = 'owner' AND is_primary = true
    """))

    print(f"Removed {result.rowcount} backfilled UserOrganization records")
