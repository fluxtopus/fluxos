"""add_oauth_social_login_system

Revision ID: 866ca41b19ce
Revises: af97b02d8f93
Create Date: 2025-11-30 04:54:29.530739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '866ca41b19ce'
down_revision: Union[str, None] = 'af97b02d8f93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create oauth_providers table
    op.create_table(
        'oauth_providers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider_name', sa.String(50), nullable=False),
        sa.Column('client_id', sa.String(255), nullable=False),
        sa.Column('client_secret', sa.String(255), nullable=False),
        sa.Column('authorization_url', sa.String(500), nullable=False),
        sa.Column('token_url', sa.String(500), nullable=False),
        sa.Column('user_info_url', sa.String(500), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_name', name='uq_provider_name')
    )

    # Create oauth_accounts table
    op.create_table(
        'oauth_accounts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=False),
        sa.Column('provider_user_id', sa.String(255), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('profile_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['provider_id'], ['oauth_providers.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_id', 'provider_user_id', name='uq_provider_user')
    )

    # Create user_organizations table for multi-org support
    op.create_table(
        'user_organizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'organization_id', name='uq_user_org')
    )

    # Make password_hash nullable for OAuth-only users
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(),
                    nullable=True)

    # Create indexes for performance
    op.create_index('ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'])
    op.create_index('ix_oauth_accounts_provider_id', 'oauth_accounts', ['provider_id'])
    op.create_index('ix_user_organizations_user_id', 'user_organizations', ['user_id'])
    op.create_index('ix_user_organizations_organization_id', 'user_organizations', ['organization_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_user_organizations_organization_id', 'user_organizations')
    op.drop_index('ix_user_organizations_user_id', 'user_organizations')
    op.drop_index('ix_oauth_accounts_provider_id', 'oauth_accounts')
    op.drop_index('ix_oauth_accounts_user_id', 'oauth_accounts')

    # Make password_hash non-nullable again
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(),
                    nullable=False)

    # Drop tables
    op.drop_table('user_organizations')
    op.drop_table('oauth_accounts')
    op.drop_table('oauth_providers')

