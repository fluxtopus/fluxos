"""Add twitter to integration_provider_enum.

Revision ID: 006
Revises: 005
Create Date: 2026-01-31
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE integration_provider_enum ADD VALUE IF NOT EXISTS 'twitter'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'twitter' value will remain but be unused after downgrade.
    pass
