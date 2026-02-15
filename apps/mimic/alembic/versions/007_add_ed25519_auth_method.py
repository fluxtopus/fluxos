"""Add ed25519 to inbound_auth_method_enum.

Revision ID: 007
Revises: 006
Create Date: 2026-02-04
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE inbound_auth_method_enum ADD VALUE IF NOT EXISTS 'ed25519'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'ed25519' value will remain but be unused after downgrade.
    pass
