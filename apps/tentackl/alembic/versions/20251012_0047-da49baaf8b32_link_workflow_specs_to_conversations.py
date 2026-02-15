"""link_workflow_specs_to_conversations

Revision ID: da49baaf8b32
Revises: 3c88722f4315
Create Date: 2025-10-12 00:47:23.378407

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "da49baaf8b32"
down_revision = "3c88722f4315"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add conversation_id column to workflow_specs table
    op.add_column(
        'workflow_specs',
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Create foreign key constraint to conversations table
    op.create_foreign_key(
        'fk_workflow_specs_conversation_id',
        'workflow_specs',
        'conversations',
        ['conversation_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Create index for fast conversation → specs lookups
    op.create_index(
        'idx_wf_spec_conversation',
        'workflow_specs',
        ['conversation_id']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_wf_spec_conversation', 'workflow_specs')

    # Drop foreign key constraint
    op.drop_constraint('fk_workflow_specs_conversation_id', 'workflow_specs', type_='foreignkey')

    # Drop column
    op.drop_column('workflow_specs', 'conversation_id')
