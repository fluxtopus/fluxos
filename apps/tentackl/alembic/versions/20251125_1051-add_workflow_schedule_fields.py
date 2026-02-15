"""add_workflow_schedule_fields

Revision ID: add_workflow_schedule_fields
Revises: c43797c75e38
Create Date: 2025-11-25 10:51:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "add_workflow_schedule_fields"
down_revision = "c43797c75e38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add schedule fields to workflow_specs table
    op.add_column('workflow_specs', sa.Column('schedule_cron', sa.String(255), nullable=True))
    op.add_column('workflow_specs', sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('workflow_specs', sa.Column('schedule_timezone', sa.String(50), nullable=False, server_default='UTC'))
    op.add_column('workflow_specs', sa.Column('last_scheduled_run_at', sa.DateTime(), nullable=True))
    op.add_column('workflow_specs', sa.Column('next_scheduled_run_at', sa.DateTime(), nullable=True))
    
    # Create index for efficient querying of active scheduled workflows
    op.create_index(
        'idx_wf_spec_schedule_enabled',
        'workflow_specs',
        ['is_active', 'schedule_enabled'],
        unique=False
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_wf_spec_schedule_enabled', 'workflow_specs')
    
    # Drop schedule columns
    op.drop_column('workflow_specs', 'next_scheduled_run_at')
    op.drop_column('workflow_specs', 'last_scheduled_run_at')
    op.drop_column('workflow_specs', 'schedule_timezone')
    op.drop_column('workflow_specs', 'schedule_enabled')
    op.drop_column('workflow_specs', 'schedule_cron')

