"""Add user invitations table

Revision ID: 20260115_invitations
Revises: 20260114_add_permission_templates
Create Date: 2026-01-15

Adds invitations table for email-based user onboarding.
Admins can invite users to their organization with a specific role.
"""

from alembic import op
import sqlalchemy as sa

revision = '20260115_invitations'
down_revision = '20260114_templates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'invitations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('token_hash', sa.String(), unique=True, nullable=False),
        sa.Column('invited_by_user_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('accepted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invitations_organization_id', 'invitations', ['organization_id'])
    op.create_index('ix_invitations_email', 'invitations', ['email'])
    op.create_index('ix_invitations_token_hash', 'invitations', ['token_hash'])
    op.create_index('ix_invitations_status', 'invitations', ['status'])


def downgrade() -> None:
    op.drop_index('ix_invitations_status', table_name='invitations')
    op.drop_index('ix_invitations_token_hash', table_name='invitations')
    op.drop_index('ix_invitations_email', table_name='invitations')
    op.drop_index('ix_invitations_organization_id', table_name='invitations')
    op.drop_table('invitations')
