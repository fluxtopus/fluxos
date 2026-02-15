"""CAP-003: Add semantic search columns to capabilities_agents

Revision ID: 20260125_cap003
Revises: 20260125_cap002
Create Date: 2026-01-25 15:00:00.000000

Adds columns for semantic search and discovery:
- description_embedding: Vector(1536) for semantic similarity search
- embedding_status: Status of embedding generation (pending/generated/failed)
- keywords: Array of search keywords for fallback text search
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = '20260125_cap003'
down_revision = '20260125_cap002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add semantic search columns to capabilities_agents table."""
    # description_embedding - Vector for semantic similarity search
    # Uses 1536 dimensions to match OpenAI ada-002 embedding model
    op.add_column(
        'capabilities_agents',
        sa.Column('description_embedding', Vector(1536), nullable=True)
    )

    # embedding_status - Track embedding generation progress
    # Values: pending, generated, failed
    op.add_column(
        'capabilities_agents',
        sa.Column('embedding_status', sa.String(50), nullable=True, server_default='pending')
    )

    # keywords - Array of search keywords for fallback text search
    op.add_column(
        'capabilities_agents',
        sa.Column('keywords', sa.ARRAY(sa.String(100)), nullable=True, server_default='{}')
    )

    # Create index for embedding_status to filter by generation state
    op.create_index(
        'idx_cap_agents_embedding_status',
        'capabilities_agents',
        ['embedding_status'],
        unique=False
    )

    # Create GIN index for keywords array for efficient containment queries
    op.create_index(
        'idx_cap_agents_keywords',
        'capabilities_agents',
        ['keywords'],
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Remove semantic search columns from capabilities_agents table."""
    op.drop_index('idx_cap_agents_keywords', table_name='capabilities_agents')
    op.drop_index('idx_cap_agents_embedding_status', table_name='capabilities_agents')

    op.drop_column('capabilities_agents', 'keywords')
    op.drop_column('capabilities_agents', 'embedding_status')
    op.drop_column('capabilities_agents', 'description_embedding')
