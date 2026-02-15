"""CAP-001: Add management columns to capabilities_agents

Revision ID: 20260125_cap001
Revises: 20260125_integration
Create Date: 2026-01-25 13:00:00.000000

Adds columns needed for user management:
- version: For versioning capabilities
- is_latest: Flag to identify latest version
- created_by: Audit trail (user ID reference)
- tags: Array of tags for filtering
- spec_yaml: Original YAML for editing
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260125_cap001'
down_revision = 'add_agent_ownership'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add management columns to capabilities_agents table."""
    # Version column - integer starting at 1
    op.add_column(
        'capabilities_agents',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1')
    )

    # is_latest flag - true by default for new entries
    op.add_column(
        'capabilities_agents',
        sa.Column('is_latest', sa.Boolean(), nullable=False, server_default='true')
    )

    # created_by - UUID reference to the user who created this capability
    op.add_column(
        'capabilities_agents',
        sa.Column('created_by', sa.UUID(), nullable=True)
    )

    # tags - array of strings for categorization/filtering
    op.add_column(
        'capabilities_agents',
        sa.Column('tags', postgresql.ARRAY(sa.String(50)), nullable=True, server_default='{}')
    )

    # spec_yaml - original YAML specification for editing
    op.add_column(
        'capabilities_agents',
        sa.Column('spec_yaml', sa.Text(), nullable=True)
    )

    # Add indexes for efficient querying
    op.create_index(
        'idx_cap_agents_version',
        'capabilities_agents',
        ['version'],
        unique=False
    )

    op.create_index(
        'idx_cap_agents_is_latest',
        'capabilities_agents',
        ['is_latest'],
        unique=False
    )

    op.create_index(
        'idx_cap_agents_created_by',
        'capabilities_agents',
        ['created_by'],
        unique=False
    )

    # GIN index for tags array for efficient contains/overlap queries
    op.create_index(
        'idx_cap_agents_tags',
        'capabilities_agents',
        ['tags'],
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Remove management columns from capabilities_agents table."""
    op.drop_index('idx_cap_agents_tags', table_name='capabilities_agents')
    op.drop_index('idx_cap_agents_created_by', table_name='capabilities_agents')
    op.drop_index('idx_cap_agents_is_latest', table_name='capabilities_agents')
    op.drop_index('idx_cap_agents_version', table_name='capabilities_agents')

    op.drop_column('capabilities_agents', 'spec_yaml')
    op.drop_column('capabilities_agents', 'tags')
    op.drop_column('capabilities_agents', 'created_by')
    op.drop_column('capabilities_agents', 'is_latest')
    op.drop_column('capabilities_agents', 'version')
