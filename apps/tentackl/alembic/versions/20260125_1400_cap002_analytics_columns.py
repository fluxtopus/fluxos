"""CAP-002: Add analytics columns to capabilities_agents

Revision ID: 20260125_cap002
Revises: 20260125_cap001
Create Date: 2026-01-25 14:00:00.000000

Adds columns for usage tracking:
- usage_count: Total number of times this capability was used
- success_count: Number of successful executions
- failure_count: Number of failed executions
- last_used_at: Timestamp of last usage
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260125_cap002'
down_revision = '20260125_cap001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add analytics columns to capabilities_agents table."""
    # usage_count - total times this capability was used
    op.add_column(
        'capabilities_agents',
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0')
    )

    # success_count - number of successful executions
    op.add_column(
        'capabilities_agents',
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0')
    )

    # failure_count - number of failed executions
    op.add_column(
        'capabilities_agents',
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0')
    )

    # last_used_at - timestamp of last usage
    op.add_column(
        'capabilities_agents',
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add index for last_used_at for efficient recent-usage queries
    op.create_index(
        'idx_cap_agents_last_used_at',
        'capabilities_agents',
        ['last_used_at'],
        unique=False
    )


def downgrade() -> None:
    """Remove analytics columns from capabilities_agents table."""
    op.drop_index('idx_cap_agents_last_used_at', table_name='capabilities_agents')

    op.drop_column('capabilities_agents', 'last_used_at')
    op.drop_column('capabilities_agents', 'failure_count')
    op.drop_column('capabilities_agents', 'success_count')
    op.drop_column('capabilities_agents', 'usage_count')
