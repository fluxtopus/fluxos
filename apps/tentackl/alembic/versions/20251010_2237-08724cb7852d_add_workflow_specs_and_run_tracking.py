"""add_workflow_specs_and_run_tracking

Revision ID: 08724cb7852d
Revises: a20251005ver
Create Date: 2025-10-10 22:37:57.094536

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "08724cb7852d"
down_revision = "a20251005ver"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create workflow_specs table
    op.create_table(
        'workflow_specs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('spec_yaml', sa.Text(), nullable=False),
        sa.Column('spec_compiled', sa.JSON(), nullable=False),
        sa.Column('version', sa.String(50), nullable=False, server_default='1.0.0'),
        sa.Column('labels', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('source', sa.String(50), nullable=True, server_default='file'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes for workflow_specs
    op.create_index('idx_wf_spec_name', 'workflow_specs', ['name'])
    op.create_index('idx_wf_spec_active', 'workflow_specs', ['is_active'])
    op.create_index('idx_wf_spec_created', 'workflow_specs', ['created_at'])

    # 2. Add new columns to workflows table for run tracking
    op.add_column('workflows', sa.Column('spec_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('workflows', sa.Column('run_number', sa.Integer(), nullable=True))
    op.add_column('workflows', sa.Column('spec_name', sa.String(255), nullable=True))
    op.add_column('workflows', sa.Column('run_parameters', sa.JSON(), nullable=True))
    op.add_column('workflows', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('workflows', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.add_column('workflows', sa.Column('triggered_by', sa.String(50), nullable=True, server_default='manual'))

    # 3. Create foreign key constraint
    op.create_foreign_key(
        'fk_workflows_spec_id',
        'workflows',
        'workflow_specs',
        ['spec_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 4. Create indexes for workflows
    op.create_index('idx_workflow_spec_id', 'workflows', ['spec_id'])
    op.create_index('idx_workflow_spec_name', 'workflows', ['spec_name'])
    op.create_index('idx_workflow_run_number', 'workflows', ['spec_id', 'run_number'])
    op.create_index('idx_workflow_triggered_by', 'workflows', ['triggered_by'])
    op.create_index('idx_workflow_started_at', 'workflows', ['started_at'])

    # 5. Migrate existing workflows (optional data migration)
    # Set existing workflows with triggered_by='legacy' to indicate they were created before this migration
    # This is done via raw SQL to avoid issues with ORM
    # Safe for empty tables: UPDATE with WHERE clause returns 0 rows updated if table is empty
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE workflows SET triggered_by = 'legacy' WHERE triggered_by IS NULL"
    ))


def downgrade() -> None:
    # Drop indexes from workflows
    op.drop_index('idx_workflow_started_at', 'workflows')
    op.drop_index('idx_workflow_triggered_by', 'workflows')
    op.drop_index('idx_workflow_run_number', 'workflows')
    op.drop_index('idx_workflow_spec_name', 'workflows')
    op.drop_index('idx_workflow_spec_id', 'workflows')

    # Drop foreign key constraint
    op.drop_constraint('fk_workflows_spec_id', 'workflows', type_='foreignkey')

    # Drop new columns from workflows
    op.drop_column('workflows', 'triggered_by')
    op.drop_column('workflows', 'completed_at')
    op.drop_column('workflows', 'started_at')
    op.drop_column('workflows', 'run_parameters')
    op.drop_column('workflows', 'spec_name')
    op.drop_column('workflows', 'run_number')
    op.drop_column('workflows', 'spec_id')

    # Drop indexes from workflow_specs
    op.drop_index('idx_wf_spec_created', 'workflow_specs')
    op.drop_index('idx_wf_spec_active', 'workflow_specs')
    op.drop_index('idx_wf_spec_name', 'workflow_specs')

    # Drop workflow_specs table
    op.drop_table('workflow_specs')
