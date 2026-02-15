"""Create memory service tables.

Creates the three tables for the Memory Service:
- memories: Knowledge artifacts stored by users and agents
- memory_versions: Version history for memory content
- memory_permissions: Access control for individual memories

Does NOT include pgvector columns - those are added in a separate migration (MEM-025).

Revision ID: memory_001
Revises: automations_002
Create Date: 2026-02-02 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "memory_001"
down_revision = "automations_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create memories table
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("key", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(50), nullable=False, server_default="organization"),
        sa.Column("scope_value", sa.String(255), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("topic", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="text"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_by_agent_id", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Indexes for memories table
    op.create_index("idx_memory_org", "memories", ["organization_id"])
    op.create_unique_constraint("idx_memory_org_key", "memories", ["organization_id", "key"])
    op.create_index("idx_memory_scope", "memories", ["scope"])
    op.create_index("idx_memory_org_scope", "memories", ["organization_id", "scope", "scope_value"])
    op.create_index("idx_memory_topic", "memories", ["topic"])
    op.create_index(
        "idx_memory_tags",
        "memories",
        ["tags"],
        postgresql_using="gin"
    )
    op.create_index("idx_memory_created", "memories", ["created_at"])
    op.create_index("idx_memory_created_by_user", "memories", ["created_by_user_id"])
    op.create_index("idx_memory_created_by_agent", "memories", ["created_by_agent_id"])

    # Create memory_versions table
    op.create_table(
        "memory_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("extended_data", postgresql.JSON(), nullable=True),
        sa.Column("change_summary", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.String(255), nullable=True),
        sa.Column("changed_by_agent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Unique constraint for memory_versions
    op.create_unique_constraint("uq_memory_version", "memory_versions", ["memory_id", "version"])
    op.create_index("idx_memver_memory", "memory_versions", ["memory_id"])

    # Create memory_permissions table
    op.create_table(
        "memory_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("grantee_user_id", sa.String(255), nullable=True),
        sa.Column("grantee_agent_id", sa.String(255), nullable=True),
        sa.Column("permission_level", sa.String(50), nullable=False, server_default="read"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Indexes for memory_permissions table
    op.create_index("idx_memperm_memory", "memory_permissions", ["memory_id"])
    op.create_index("idx_memperm_user", "memory_permissions", ["grantee_user_id"])
    op.create_index("idx_memperm_agent", "memory_permissions", ["grantee_agent_id"])


def downgrade() -> None:
    # Drop memory_permissions table first (depends on memories)
    op.drop_index("idx_memperm_agent", table_name="memory_permissions")
    op.drop_index("idx_memperm_user", table_name="memory_permissions")
    op.drop_index("idx_memperm_memory", table_name="memory_permissions")
    op.drop_table("memory_permissions")

    # Drop memory_versions table (depends on memories)
    op.drop_index("idx_memver_memory", table_name="memory_versions")
    op.drop_constraint("uq_memory_version", "memory_versions", type_="unique")
    op.drop_table("memory_versions")

    # Drop memories table last
    op.drop_index("idx_memory_created_by_agent", table_name="memories")
    op.drop_index("idx_memory_created_by_user", table_name="memories")
    op.drop_index("idx_memory_created", table_name="memories")
    op.drop_index("idx_memory_tags", table_name="memories")
    op.drop_index("idx_memory_topic", table_name="memories")
    op.drop_index("idx_memory_org_scope", table_name="memories")
    op.drop_index("idx_memory_scope", table_name="memories")
    op.drop_constraint("idx_memory_org_key", "memories", type_="unique")
    op.drop_index("idx_memory_org", table_name="memories")
    op.drop_table("memories")
