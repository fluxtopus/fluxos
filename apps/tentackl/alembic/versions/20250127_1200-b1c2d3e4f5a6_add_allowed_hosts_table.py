"""add_allowed_hosts_table

Revision ID: b1c2d3e4f5a6
Revises: aa9c7be64c84
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "aa9c7be64c84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create allowed_hosts table
    op.create_table(
        "allowed_hosts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column(
            "environment",
            sa.Enum("development", "production", "staging", "testing", name="environment"),
            nullable=False,
            server_default="development"
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    
    # Create indexes
    op.create_index("idx_allowed_host_host_env", "allowed_hosts", ["host", "environment"])
    op.create_index("idx_allowed_host_enabled", "allowed_hosts", ["enabled"])
    op.create_index("idx_allowed_host_environment", "allowed_hosts", ["environment"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_allowed_host_environment", "allowed_hosts")
    op.drop_index("idx_allowed_host_enabled", "allowed_hosts")
    op.drop_index("idx_allowed_host_host_env", "allowed_hosts")
    
    # Drop table
    op.drop_table("allowed_hosts")
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS environment")

