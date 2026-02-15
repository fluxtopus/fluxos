"""add version column to workflows

Revision ID: add_version_to_workflows_20251005
Revises: 2a0e84a5fd94
Create Date: 2025-10-05 00:11:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a20251005ver"
down_revision = "2a0e84a5fd94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add version column with default 0
    op.add_column(
        "workflows",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    # Remove server_default after column is created (PostgreSQL-compatible)
    # For fresh databases, this ensures clean column definition
    op.alter_column("workflows", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("workflows", "version")
