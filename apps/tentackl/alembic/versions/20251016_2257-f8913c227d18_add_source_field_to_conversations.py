"""add_source_field_to_conversations

Revision ID: f8913c227d18
Revises: da49baaf8b32
Create Date: 2025-10-16 22:57:34.441400

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f8913c227d18"
down_revision = "da49baaf8b32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add source column to conversations table (nullable initially for backward compatibility)
    op.add_column('conversations', sa.Column('source', sa.String(50), nullable=True))

    # Backfill existing data based on trigger_source and root_agent_id
    # - "arrow_chat" or "copilot-ui" becomes "arrow" (user-initiated conversations)
    # - Everything else becomes "workflow" (agent/workflow-generated)
    # Safe for empty tables: UPDATE with WHERE clause returns 0 rows updated if table is empty
    op.execute("""
        UPDATE conversations
        SET source = CASE
            WHEN trigger_source IN ('arrow_chat', 'copilot-ui') THEN 'arrow'
            WHEN root_agent_id = 'copilot' OR root_agent_id = 'arrow' THEN 'arrow'
            ELSE 'workflow'
        END
        WHERE source IS NULL
    """)

    # Now make the column non-nullable with default value
    op.alter_column('conversations', 'source', nullable=False, server_default='workflow')

    # Add index for efficient filtering by source
    op.create_index('idx_conversation_source', 'conversations', ['source'])


def downgrade() -> None:
    # Remove index
    op.drop_index('idx_conversation_source', 'conversations')

    # Remove column
    op.drop_column('conversations', 'source')
