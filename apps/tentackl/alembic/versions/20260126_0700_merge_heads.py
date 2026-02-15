"""Merge migration heads.

Revision ID: 20260126_merge
Revises: 20260126_cap006, 20260125_integration
Create Date: 2026-01-26 07:00:00.000000

Merges the capability versioning (cap006) and task integration branches.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260126_merge'
down_revision = ('20260126_cap006', '20260125_integration')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge heads - no schema changes needed."""
    pass


def downgrade() -> None:
    """Merge heads - no schema changes needed."""
    pass
