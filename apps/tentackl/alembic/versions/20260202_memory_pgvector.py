"""Add pgvector support to memories table.

Adds vector embedding column and HNSW index for semantic memory search.

MEM-025: Enables semantic similarity search in the Memory Service by:
- Enabling pgvector extension
- Adding content_embedding column (vector 1536) for OpenAI text-embedding-3-small
- Adding embedding_status column to track generation status
- Creating HNSW index for fast cosine similarity search

Revision ID: memory_002
Revises: memory_001
Create Date: 2026-02-02 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "memory_002"
down_revision = "memory_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pgvector columns and HNSW index to memories table."""
    # Ensure pgvector extension is enabled
    # This is idempotent - safe to run if extension already exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add content_embedding column for semantic search
    # Uses 1536 dimensions for OpenAI text-embedding-3-small
    op.execute("ALTER TABLE memories ADD COLUMN content_embedding vector(1536)")

    # Add embedding_status column to track embedding generation
    # Values: pending (default), completed, failed
    op.add_column(
        "memories",
        sa.Column(
            "embedding_status",
            sa.String(50),
            nullable=True,
            server_default="pending"
        )
    )

    # Create HNSW index for fast vector similarity search
    # HNSW parameters:
    # - m=16: Number of bi-directional links per node (higher = more accurate but slower builds)
    # - ef_construction=64: Size of dynamic candidate list during construction
    # Using vector_cosine_ops for cosine similarity (normalized vectors)
    op.execute("""
        CREATE INDEX idx_memory_embedding
        ON memories USING hnsw (content_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Add index on embedding_status for filtering by generation state
    op.create_index(
        "idx_memory_embedding_status",
        "memories",
        ["embedding_status"]
    )


def downgrade() -> None:
    """Remove pgvector columns and indexes from memories table."""
    # Drop indexes first
    op.drop_index("idx_memory_embedding_status", table_name="memories")
    op.execute("DROP INDEX IF EXISTS idx_memory_embedding")

    # Drop columns
    op.drop_column("memories", "embedding_status")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS content_embedding")

    # Note: We don't drop the vector extension in downgrade because
    # other tables (tasks, capabilities_agents) may also be using it
