"""create_conversation_tables

Revision ID: 3c88722f4315
Revises: 08724cb7852d
Create Date: 2025-10-10 23:23:41.355006

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3c88722f4315"
down_revision = "08724cb7852d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types for conversation status
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE conversationstatus AS ENUM ('ACTIVE', 'COMPLETED', 'FAILED', 'CANCELLED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE triggertype AS ENUM ('EVENT', 'API_CALL', 'SCHEDULED', 'MANUAL', 'WEBHOOK', 'INTER_AGENT');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagetype AS ENUM ('LLM_PROMPT', 'LLM_RESPONSE', 'INTER_AGENT', 'TOOL_CALL', 'TOOL_RESPONSE', 'STATE_UPDATE', 'ERROR');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagedirection AS ENUM ('INBOUND', 'OUTBOUND', 'INTERNAL');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('root_agent_id', sa.String(255), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='conversationstatus', create_type=False), nullable=False),
        sa.Column('trigger_type', postgresql.ENUM(name='triggertype', create_type=False), nullable=False),
        sa.Column('trigger_source', sa.Text(), nullable=True),
        sa.Column('trigger_details', sa.JSON(), nullable=True),
        sa.Column('extra_metadata', sa.JSON(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['parent_conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    )

    # Create indexes for conversations
    op.create_index('idx_conversation_status', 'conversations', ['status'])
    op.create_index('idx_conversation_time_range', 'conversations', ['start_time', 'end_time'])
    op.create_index('idx_conversation_workflow', 'conversations', ['workflow_id'])
    op.create_index('idx_conversation_tags', 'conversations', ['tags'], postgresql_using='gin')

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.String(255), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('message_type', postgresql.ENUM(name='messagetype', create_type=False), nullable=False),
        sa.Column('direction', postgresql.ENUM(name='messagedirection', create_type=False), nullable=False),
        sa.Column('role', sa.String(20), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('content_data', sa.JSON(), nullable=True),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('masked_fields', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cost_amount', sa.DECIMAL(10, 6), nullable=True),
        sa.Column('cost_currency', sa.String(3), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('extra_metadata', sa.JSON(), nullable=True),
        sa.Column('parent_message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_message_id'], ['messages.id'], ondelete='SET NULL'),
    )

    # Create indexes for messages
    op.create_index('idx_message_conversation_timestamp', 'messages', ['conversation_id', 'timestamp'])
    op.create_index('idx_message_agent_timestamp', 'messages', ['agent_id', 'timestamp'])
    op.create_index('idx_message_message_type', 'messages', ['message_type'])
    op.create_index('idx_message_timestamp', 'messages', ['timestamp'])

    # Create conversation_metrics table
    op.create_table(
        'conversation_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('total_messages', sa.Integer(), nullable=True),
        sa.Column('total_llm_calls', sa.Integer(), nullable=True),
        sa.Column('total_tool_calls', sa.Integer(), nullable=True),
        sa.Column('total_errors', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('total_cost', sa.DECIMAL(10, 6), nullable=True),
        sa.Column('average_latency_ms', sa.Float(), nullable=True),
        sa.Column('max_latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    )

    # Create index for conversation_metrics
    op.create_index('idx_metrics_conversation', 'conversation_metrics', ['conversation_id'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('conversation_metrics')
    op.drop_table('messages')
    op.drop_table('conversations')

    # Drop enum types
    op.execute('DROP TYPE IF EXISTS conversationstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS triggertype CASCADE')
    op.execute('DROP TYPE IF EXISTS messagetype CASCADE')
    op.execute('DROP TYPE IF EXISTS messagedirection CASCADE')
