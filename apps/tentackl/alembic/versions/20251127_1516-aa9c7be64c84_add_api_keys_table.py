"""add_api_keys_table

Revision ID: aa9c7be64c84
Revises: 624afa178dcc
Create Date: 2025-11-27 15:16:06.908830

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "aa9c7be64c84"
down_revision = "624afa178dcc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True, server_default="{}"),
    )
    
    # Create unique constraint on key_hash
    op.create_unique_constraint("uq_api_key_hash", "api_keys", ["key_hash"])
    
    # Create indexes
    op.create_index("idx_api_key_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_key_service", "api_keys", ["service_name"])
    op.create_index("idx_api_key_active", "api_keys", ["is_active"])
    op.create_index("idx_api_key_expires", "api_keys", ["expires_at"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_api_key_expires", "api_keys")
    op.drop_index("idx_api_key_active", "api_keys")
    op.drop_index("idx_api_key_service", "api_keys")
    op.drop_index("idx_api_key_hash", "api_keys")
    
    # Drop table
    op.drop_table("api_keys")
