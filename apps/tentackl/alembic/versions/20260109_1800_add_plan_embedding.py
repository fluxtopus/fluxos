"""Add embedding column for semantic task search

Revision ID: 20260109_embedding
Revises: f1a2b3c4d5e6
Create Date: 2026-01-09

Adds:
- goal_embedding column (vector 1536) for semantic similarity search
- embedding_status column to track generation status
- HNSW index for fast vector similarity search

This enables "do the HN thing again" pattern recognition by finding
similar past tasks based on goal embeddings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260109_embedding'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add goal_embedding column for semantic search
    # Uses 1536 dimensions for OpenAI text-embedding-3-small
    op.execute('ALTER TABLE tasks ADD COLUMN goal_embedding vector(1536)')

    # Add embedding status column
    op.add_column('tasks', sa.Column(
        'embedding_status',
        sa.String(31),
        server_default='pending',
        nullable=False
    ))

    # Create HNSW index for fast vector similarity search
    # HNSW is faster than IVFFlat for datasets under 1M rows
    op.execute('''
        CREATE INDEX idx_tasks_embedding_hnsw
        ON tasks USING hnsw (goal_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE goal_embedding IS NOT NULL
    ''')

    # Add index on embedding_status for filtering
    op.create_index('idx_tasks_embedding_status', 'tasks', ['embedding_status'])

    # Add index for completed tasks (for similarity search)
    op.create_index(
        'idx_tasks_completed_with_embedding',
        'tasks',
        ['organization_id', 'status', 'embedding_status'],
        postgresql_where=sa.text("status = 'completed' AND embedding_status = 'ready'")
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_tasks_completed_with_embedding', table_name='tasks')
    op.drop_index('idx_tasks_embedding_status', table_name='tasks')
    op.execute('DROP INDEX IF EXISTS idx_tasks_embedding_hnsw')

    # Drop columns
    op.drop_column('tasks', 'embedding_status')
    op.execute('ALTER TABLE tasks DROP COLUMN IF EXISTS goal_embedding')
