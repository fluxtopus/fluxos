"""CAP-023: Drop agent_specs and agent_executions tables.

Revision ID: 20260126_cap023
Revises: 20260126_merge
Create Date: 2026-01-26 08:00:00.000000

As part of the capabilities unification (CAP-001 through CAP-022), all agent
specifications have been migrated to the unified capabilities_agents table.
This migration removes the legacy tables that are no longer needed.

Tables dropped:
- agent_specs: Legacy agent specification storage (replaced by capabilities_agents)
- agent_executions: Legacy execution tracking (replaced by task-based tracking)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260126_cap023'
down_revision = '20260126_merge'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop legacy agent_specs and agent_executions tables."""
    # Drop agent_executions first (it has FK to agent_specs)
    op.drop_table('agent_executions')

    # Drop agent_specs table
    op.drop_table('agent_specs')


def downgrade() -> None:
    """Recreate agent_specs and agent_executions tables.

    Note: This downgrade does NOT restore any data - it only recreates the schema.
    If you need the data, restore from backup before running downgrade.
    """
    # Recreate agent_specs table
    op.create_table(
        'agent_specs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('version', sa.String(50), nullable=False, server_default='1.0.0'),
        sa.Column('agent_type', sa.String(100), nullable=False, server_default='configurable'),
        sa.Column('spec_yaml', sa.Text(), nullable=False),
        sa.Column('spec_compiled', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True, server_default='system'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_latest', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deprecation_reason', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('category', sa.String(100), nullable=True, server_default='custom'),
        sa.Column('description_embedding', postgresql.Vector(1536), nullable=True),
        sa.Column('embedding_status', sa.String(50), nullable=True, server_default='pending'),
        sa.Column('brief', sa.String(500), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('capabilities', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('validation_status', sa.String(50), nullable=True, server_default='pending'),
        sa.Column('validation_errors', sa.JSON(), nullable=True),
        sa.Column('validation_warnings', sa.JSON(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_execution_time_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cost', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Recreate indexes
    op.create_index('idx_agent_spec_name', 'agent_specs', ['name'])
    op.create_index('idx_agent_spec_name_version', 'agent_specs', ['name', 'version'], unique=True)
    op.create_index('idx_agent_spec_active', 'agent_specs', ['is_active'])
    op.create_index('idx_agent_spec_latest', 'agent_specs', ['is_latest'])
    op.create_index('idx_agent_spec_active_latest', 'agent_specs', ['is_active', 'is_latest'])
    op.create_index('idx_agent_spec_category', 'agent_specs', ['category'])
    op.create_index('idx_agent_spec_created', 'agent_specs', ['created_at'])

    # Recreate agent_executions table
    op.create_table(
        'agent_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_spec_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('workflow_node_id', sa.String(255), nullable=True),
        sa.Column('agent_id', sa.String(255), nullable=False),
        sa.Column('execution_context', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='running'),
        sa.Column('result_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('memory_mb_peak', sa.Integer(), nullable=True),
        sa.Column('success_metrics', sa.JSON(), nullable=True),
        sa.Column('all_metrics_passed', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_spec_id'], ['agent_specs.id'], ondelete='CASCADE'),
    )

    # Recreate indexes
    op.create_index('idx_agent_exec_spec_id', 'agent_executions', ['agent_spec_id'])
    op.create_index('idx_agent_exec_workflow', 'agent_executions', ['workflow_id'])
    op.create_index('idx_agent_exec_status', 'agent_executions', ['status'])
    op.create_index('idx_agent_exec_started', 'agent_executions', ['started_at'])
    op.create_index('idx_agent_exec_completed', 'agent_executions', ['completed_at'])
    op.create_index('idx_agent_exec_spec_status', 'agent_executions', ['agent_spec_id', 'status'])
