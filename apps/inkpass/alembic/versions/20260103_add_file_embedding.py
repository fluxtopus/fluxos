"""Add embedding column for semantic search

Revision ID: 20260103_embedding
Revises: 20250130_files
Create Date: 2026-01-03

Adds:
- embedding column (vector 1536) for OpenAI text-embedding-3-small
- embedding_status column to track generation status
- HNSW index for fast vector similarity search
- GIN trigram index for filename pattern matching
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260103_embedding'
down_revision: Union[str, None] = '20250130_files'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled (should be done in init script, but safe to run again)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # Add embedding column for semantic search
    # Uses 1536 dimensions for OpenAI text-embedding-3-small
    op.execute('ALTER TABLE files ADD COLUMN embedding vector(1536)')

    # Add embedding status column
    op.add_column('files', sa.Column(
        'embedding_status',
        sa.String(31),
        server_default='pending',
        nullable=False
    ))

    # Create HNSW index for fast vector similarity search
    # HNSW is faster than IVFFlat for datasets under 1M rows
    op.execute('''
        CREATE INDEX idx_files_embedding_hnsw
        ON files USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
    ''')

    # Create GIN trigram index for filename pattern matching (ILIKE)
    op.execute('''
        CREATE INDEX idx_files_name_trgm
        ON files USING gin (name gin_trgm_ops)
    ''')

    # Add index on embedding_status for filtering
    op.create_index('idx_files_embedding_status', 'files', ['embedding_status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_files_embedding_status', table_name='files')
    op.execute('DROP INDEX IF EXISTS idx_files_name_trgm')
    op.execute('DROP INDEX IF EXISTS idx_files_embedding_hnsw')

    # Drop columns
    op.drop_column('files', 'embedding_status')
    op.execute('ALTER TABLE files DROP COLUMN IF EXISTS embedding')
