"""add_workflow_management_tables

Revision ID: 2a0e84a5fd94
Revises: 
Create Date: 2025-09-15 03:26:13.026777

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "2a0e84a5fd94"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if enum already exists
    connection = op.get_bind()
    result = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflowstatus')"
    ))
    enum_exists = result.scalar()
    
    if not enum_exists:
        # Create WorkflowStatus enum
        workflow_status_enum = postgresql.ENUM(
            'pending', 'running', 'waiting', 'paused', 'completed', 
            'failed', 'cancelled', 'timeout',
            name='workflowstatus'
        )
        workflow_status_enum.create(connection)
    
    # Check if workflows table exists
    result = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflows')"
    ))
    workflows_exists = result.scalar()
    
    if not workflows_exists:
        # Create workflows table
        # Use postgresql.ENUM with create_type=False to reference the already-created enum
        workflow_status_type = postgresql.ENUM(
            'pending', 'running', 'waiting', 'paused', 'completed',
            'failed', 'cancelled', 'timeout',
            name='workflowstatus',
            create_type=False  # Don't try to create the type, it already exists
        )

        op.create_table(
            'workflows',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('status', workflow_status_type, nullable=False, server_default='pending'),
            sa.Column('config', sa.JSON(), nullable=True),
            sa.Column('state_data', sa.JSON(), nullable=True),
            sa.Column('waiting_for', sa.JSON(), nullable=True),
            sa.Column('timeout_at', sa.DateTime(), nullable=True),
            sa.Column('parent_workflow_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(['parent_workflow_id'], ['workflows.id']),
        )
    
        # Create indexes for workflows
        op.create_index('idx_workflow_status', 'workflows', ['status'])
        op.create_index('idx_workflow_parent', 'workflows', ['parent_workflow_id'])
        op.create_index('idx_workflow_timeout', 'workflows', ['timeout_at'])
        op.create_index('idx_workflow_created', 'workflows', ['created_at'])
    
    # Check and create workflow_agents table
    result = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_agents')"
    ))
    if not result.scalar():
        op.create_table(
            'workflow_agents',
            sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('agent_id', sa.String(255), nullable=False),
            sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('role', sa.String(50), nullable=False, default='peer'),
            sa.Column('registered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('metadata', sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id']),
            sa.PrimaryKeyConstraint('workflow_id', 'agent_id'),
            sa.UniqueConstraint('conversation_id', name='uq_conversation_id')
        )
        
        # Create indexes for workflow_agents
        op.create_index('idx_workflow_agent_conversation', 'workflow_agents', ['conversation_id'])
        op.create_index('idx_workflow_agent_role', 'workflow_agents', ['role'])
    
    # Check and create workflow_events table
    result = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_events')"
    ))
    if not result.scalar():
        op.create_table(
            'workflow_events',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('event_type', sa.String(100), nullable=False),
            sa.Column('event_data', sa.JSON(), nullable=True),
            sa.Column('metadata', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id']),
        )
        
        # Create indexes for workflow_events
        op.create_index('idx_workflow_event_type', 'workflow_events', ['event_type'])
        op.create_index('idx_workflow_event_created', 'workflow_events', ['created_at'])
        op.create_index('idx_workflow_event_workflow', 'workflow_events', ['workflow_id', 'created_at'])
    
    # Check and create external_publishers table
    result = connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'external_publishers')"
    ))
    if not result.scalar():
        op.create_table(
            'external_publishers',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False, unique=True),
            sa.Column('api_key_hash', sa.String(255), nullable=False, unique=True),
            sa.Column('permissions', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
            sa.Column('rate_limit', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )
        
        # Create indexes for external_publishers
        op.create_index('idx_publisher_api_key', 'external_publishers', ['api_key_hash'])
        op.create_index('idx_publisher_active', 'external_publishers', ['is_active'])


def downgrade() -> None:
    # Drop all indexes
    op.drop_index('idx_publisher_active', 'external_publishers')
    op.drop_index('idx_publisher_api_key', 'external_publishers')
    op.drop_index('idx_workflow_event_workflow', 'workflow_events')
    op.drop_index('idx_workflow_event_created', 'workflow_events')
    op.drop_index('idx_workflow_event_type', 'workflow_events')
    op.drop_index('idx_workflow_agent_role', 'workflow_agents')
    op.drop_index('idx_workflow_agent_conversation', 'workflow_agents')
    op.drop_index('idx_workflow_created', 'workflows')
    op.drop_index('idx_workflow_timeout', 'workflows')
    op.drop_index('idx_workflow_parent', 'workflows')
    op.drop_index('idx_workflow_status', 'workflows')
    
    # Drop all tables
    op.drop_table('external_publishers')
    op.drop_table('workflow_events')
    op.drop_table('workflow_agents')
    op.drop_table('workflows')
    
    # Drop enum type if exists
    workflow_status_enum = postgresql.ENUM(name='workflowstatus')
    workflow_status_enum.drop(op.get_bind(), checkfirst=True)
