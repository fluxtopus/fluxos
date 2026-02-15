"""Add integration_id to tasks table

Revision ID: 20260125_integration
Revises: add_agent_ownership
Create Date: 2026-01-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260125_integration'
down_revision = 'add_agent_ownership'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add integration_id column to tasks table."""
    # Add integration_id column to link tasks to external integrations (e.g., from Mimic)
    op.add_column(
        'tasks',
        sa.Column('integration_id', sa.String(255), nullable=True)
    )

    # Add index for efficient querying by integration
    op.create_index(
        'idx_task_integration',
        'tasks',
        ['integration_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove integration_id column from tasks table."""
    op.drop_index('idx_task_integration', table_name='tasks')
    op.drop_column('tasks', 'integration_id')
