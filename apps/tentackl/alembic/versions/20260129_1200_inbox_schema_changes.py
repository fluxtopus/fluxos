"""INBOX-004: Add inbox schema changes.

Add inbox-related columns and enums to support the Agent Inbox feature:
- readstatus enum: UNREAD, READ, ARCHIVED
- inboxpriority enum: NORMAL, ATTENTION
- conversations table: read_status, priority, user_id columns
- tasks table: conversation_id column (FK to conversations.id)
- Indexes: idx_conversation_read_status, idx_conversation_user_id,
  idx_conversation_inbox (composite), idx_task_conversation

Revision ID: inbox_001
Revises: 20260126_cap023
Create Date: 2026-01-29 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'inbox_001'
down_revision = '20260126_cap023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add inbox enums, columns, and indexes."""
    # 1. Create PostgreSQL enum types
    readstatus_enum = postgresql.ENUM(
        'unread', 'read', 'archived',
        name='readstatus',
        create_type=False,
    )
    readstatus_enum.create(op.get_bind(), checkfirst=True)

    inboxpriority_enum = postgresql.ENUM(
        'normal', 'attention',
        name='inboxpriority',
        create_type=False,
    )
    inboxpriority_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add columns to conversations table
    op.add_column(
        'conversations',
        sa.Column('read_status', sa.Enum('unread', 'read', 'archived', name='readstatus'), nullable=True),
    )
    op.add_column(
        'conversations',
        sa.Column('priority', sa.Enum('normal', 'attention', name='inboxpriority'), nullable=True),
    )
    op.add_column(
        'conversations',
        sa.Column('user_id', sa.String(255), nullable=True),
    )

    # 3. Create indexes on conversations
    op.create_index('idx_conversation_read_status', 'conversations', ['read_status'])
    op.create_index('idx_conversation_user_id', 'conversations', ['user_id'])
    op.create_index('idx_conversation_inbox', 'conversations', ['user_id', 'read_status'])

    # 4. Add conversation_id column to tasks table
    op.add_column(
        'tasks',
        sa.Column(
            'conversation_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('conversations.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )

    # 5. Create index on tasks.conversation_id
    op.create_index('idx_task_conversation', 'tasks', ['conversation_id'])


def downgrade() -> None:
    """Remove inbox enums, columns, and indexes in reverse order."""
    # 1. Drop index and column from tasks
    op.drop_index('idx_task_conversation', table_name='tasks')
    op.drop_column('tasks', 'conversation_id')

    # 2. Drop indexes from conversations
    op.drop_index('idx_conversation_inbox', table_name='conversations')
    op.drop_index('idx_conversation_user_id', table_name='conversations')
    op.drop_index('idx_conversation_read_status', table_name='conversations')

    # 3. Drop columns from conversations
    op.drop_column('conversations', 'user_id')
    op.drop_column('conversations', 'priority')
    op.drop_column('conversations', 'read_status')

    # 4. Drop enum types
    postgresql.ENUM(name='inboxpriority').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='readstatus').drop(op.get_bind(), checkfirst=True)
