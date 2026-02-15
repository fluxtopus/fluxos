"""Add organization_id and is_system columns to agent_specs table.

Revision ID: add_agent_ownership
Revises: task_unification_001
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_agent_ownership'
down_revision = 'task_unification_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add organization_id column (nullable, NULL for system agents)
    op.add_column(
        'agent_specs',
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add is_system column (default False for existing agents)
    op.add_column(
        'agent_specs',
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false')
    )

    # Add indexes for organization filtering
    op.create_index(
        'idx_agent_spec_org',
        'agent_specs',
        ['organization_id'],
        unique=False
    )

    op.create_index(
        'idx_agent_spec_org_active',
        'agent_specs',
        ['organization_id', 'is_active'],
        unique=False
    )

    op.create_index(
        'idx_agent_spec_system',
        'agent_specs',
        ['is_system'],
        unique=False
    )


def downgrade():
    # Drop indexes
    op.drop_index('idx_agent_spec_system', table_name='agent_specs')
    op.drop_index('idx_agent_spec_org_active', table_name='agent_specs')
    op.drop_index('idx_agent_spec_org', table_name='agent_specs')

    # Drop columns
    op.drop_column('agent_specs', 'is_system')
    op.drop_column('agent_specs', 'organization_id')
