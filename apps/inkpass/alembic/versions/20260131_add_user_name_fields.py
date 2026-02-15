"""Add first_name and last_name to users table

Revision ID: 20260131_user_names
Revises: 20260115_invitations
Create Date: 2026-01-31

Adds first_name and last_name columns to users table.
Nullable in DB for backward compatibility with existing users;
enforced as required at Pydantic layer for new registrations.
"""

from alembic import op
import sqlalchemy as sa

revision = '20260131_user_names'
down_revision = '20260115_invitations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
