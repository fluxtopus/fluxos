"""Task Unification - Merge Workflow/Automation into Task

This migration:
1. Adds scheduling, run tracking, analytics, and template fields to tasks table
2. Drops workflow_specs, workflows, workflow_agents, workflow_events tables

Revision ID: task_unification_001
Revises: 20260123_inkpass
Create Date: 2026-01-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'task_unification_001'
down_revision = '20260123_inkpass'
branch_labels = None
depends_on = None


def upgrade():
    # Add scheduling fields to tasks table
    op.add_column('tasks', sa.Column('schedule_cron', sa.String(255), nullable=True))
    op.add_column('tasks', sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('tasks', sa.Column('schedule_timezone', sa.String(50), nullable=False, server_default='UTC'))
    op.add_column('tasks', sa.Column('schedule_parameters', sa.JSON(), nullable=True))
    op.add_column('tasks', sa.Column('last_scheduled_run_at', sa.DateTime(), nullable=True))
    op.add_column('tasks', sa.Column('next_scheduled_run_at', sa.DateTime(), nullable=True))

    # Add run tracking fields
    op.add_column('tasks', sa.Column('run_number', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('triggered_by', sa.String(50), nullable=True, server_default='api'))
    op.add_column('tasks', sa.Column('started_at', sa.DateTime(), nullable=True))

    # Add analytics fields
    op.add_column('tasks', sa.Column('total_runs', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('tasks', sa.Column('successful_runs', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('tasks', sa.Column('failed_runs', sa.Integer(), nullable=False, server_default='0'))

    # Add template linkage fields
    op.add_column('tasks', sa.Column('template_task_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('tasks', sa.Column('is_template', sa.Boolean(), nullable=False, server_default='false'))

    # Add foreign key for template_task_id
    op.create_foreign_key(
        'fk_task_template_task',
        'tasks', 'tasks',
        ['template_task_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add indexes for scheduling queries
    op.create_index('idx_task_schedule_enabled', 'tasks', ['schedule_enabled'])
    op.create_index('idx_task_next_run', 'tasks', ['next_scheduled_run_at'])
    op.create_index('idx_task_triggered_by', 'tasks', ['triggered_by'])
    op.create_index('idx_task_template', 'tasks', ['template_task_id'])
    op.create_index('idx_task_is_template', 'tasks', ['is_template'])
    op.create_index('idx_task_user_scheduled', 'tasks', ['user_id', 'schedule_enabled'])

    # Drop FK constraints that reference workflow tables
    # prompt_evaluations references workflow_specs
    op.execute("""
        ALTER TABLE prompt_evaluations
        DROP CONSTRAINT IF EXISTS fk_prompt_eval_workflow_spec
    """)

    # Drop workflow_spec_id column from prompt_evaluations if it exists
    op.execute("""
        ALTER TABLE prompt_evaluations
        DROP COLUMN IF EXISTS workflow_spec_id
    """)

    # Drop workflow tables with CASCADE (handles any remaining FKs)
    op.execute("DROP TABLE IF EXISTS workflow_events CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS workflows CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_specs CASCADE")


def downgrade():
    # Remove indexes
    op.drop_index('idx_task_user_scheduled', table_name='tasks')
    op.drop_index('idx_task_is_template', table_name='tasks')
    op.drop_index('idx_task_template', table_name='tasks')
    op.drop_index('idx_task_triggered_by', table_name='tasks')
    op.drop_index('idx_task_next_run', table_name='tasks')
    op.drop_index('idx_task_schedule_enabled', table_name='tasks')

    # Remove foreign key
    op.drop_constraint('fk_task_template_task', 'tasks', type_='foreignkey')

    # Remove columns from tasks
    op.drop_column('tasks', 'is_template')
    op.drop_column('tasks', 'template_task_id')
    op.drop_column('tasks', 'failed_runs')
    op.drop_column('tasks', 'successful_runs')
    op.drop_column('tasks', 'total_runs')
    op.drop_column('tasks', 'started_at')
    op.drop_column('tasks', 'triggered_by')
    op.drop_column('tasks', 'run_number')
    op.drop_column('tasks', 'next_scheduled_run_at')
    op.drop_column('tasks', 'last_scheduled_run_at')
    op.drop_column('tasks', 'schedule_parameters')
    op.drop_column('tasks', 'schedule_timezone')
    op.drop_column('tasks', 'schedule_enabled')
    op.drop_column('tasks', 'schedule_cron')

    # Note: Workflow tables would need to be recreated manually in downgrade
    # This is intentionally not implemented as the migration is destructive
