"""CAP-006: Update unique constraint for capability versioning

Revision ID: 20260126_cap006
Revises: 20260125_cap003
Create Date: 2026-01-26 06:00:00.000000

Changes the unique constraint on (organization_id, agent_type) to be a
partial unique constraint that only applies when is_latest=true.
This allows multiple versions of the same capability to coexist in the
database while ensuring only one can be the "latest" version.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260126_cap006'
down_revision = '20260125_cap003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace full unique constraint with partial constraint for versioning."""
    # Drop the existing full unique constraint
    op.drop_constraint('uq_cap_agents_org_type', 'capabilities_agents', type_='unique')

    # Create partial unique index that only applies to latest versions
    # This allows old versions to coexist with same org_id + agent_type
    op.execute("""
        CREATE UNIQUE INDEX uq_cap_agents_org_type_latest
        ON capabilities_agents (organization_id, agent_type)
        WHERE is_latest = true
    """)


def downgrade() -> None:
    """Restore the original full unique constraint."""
    # Drop the partial unique index
    op.execute("DROP INDEX IF EXISTS uq_cap_agents_org_type_latest")

    # Recreate the original full unique constraint
    # Note: This may fail if there are multiple versions of the same capability
    op.create_unique_constraint(
        'uq_cap_agents_org_type',
        'capabilities_agents',
        ['organization_id', 'agent_type']
    )
