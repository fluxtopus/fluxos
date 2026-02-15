"""Initial schema

Revision ID: 33ab63e035f7
Revises:
Create Date: 2025-11-30 02:31:48.889372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '33ab63e035f7'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('settings', postgresql.JSONB(), server_default='{}'),
        sa.Column('plan_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index('idx_organizations_slug', 'organizations', ['slug'])
    op.create_index('idx_organizations_plan_id', 'organizations', ['plan_id'])

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='active'),
        sa.Column('two_fa_enabled', sa.Boolean(), server_default='false'),
        sa.Column('two_fa_secret', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE')
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_organization_id', 'users', ['organization_id'])
    op.create_index('idx_users_status', 'users', ['status'])

    # Groups table
    op.create_table(
        'groups',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_groups_org_name')
    )
    op.create_index('idx_groups_organization_id', 'groups', ['organization_id'])

    # User Groups (many-to-many)
    op.create_table(
        'user_groups',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('group_id', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'group_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE')
    )
    op.create_index('idx_user_groups_user_id', 'user_groups', ['user_id'])
    op.create_index('idx_user_groups_group_id', 'user_groups', ['group_id'])

    # Permissions table
    op.create_table(
        'permissions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('resource', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('conditions', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE')
    )
    op.create_index('idx_permissions_organization_id', 'permissions', ['organization_id'])
    op.create_index('idx_permissions_resource', 'permissions', ['resource'])
    op.create_index('idx_permissions_action', 'permissions', ['action'])

    # Group Permissions
    op.create_table(
        'group_permissions',
        sa.Column('group_id', sa.String(), nullable=False),
        sa.Column('permission_id', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('group_id', 'permission_id'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE')
    )
    op.create_index('idx_group_permissions_group_id', 'group_permissions', ['group_id'])
    op.create_index('idx_group_permissions_permission_id', 'group_permissions', ['permission_id'])

    # User Permissions (direct user permissions, override group)
    op.create_table(
        'user_permissions',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('permission_id', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'permission_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE')
    )
    op.create_index('idx_user_permissions_user_id', 'user_permissions', ['user_id'])
    op.create_index('idx_user_permissions_permission_id', 'user_permissions', ['permission_id'])

    # API Keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('scopes', postgresql.JSONB(), server_default='[]'),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_used_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_api_keys_organization_id', 'api_keys', ['organization_id'])
    op.create_index('idx_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('idx_api_keys_key_hash', 'api_keys', ['key_hash'])

    # Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('idx_sessions_token_hash', 'sessions', ['token_hash'])
    op.create_index('idx_sessions_expires_at', 'sessions', ['expires_at'])

    # OTP Codes table
    op.create_table(
        'otp_codes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('code_hash', sa.String(), nullable=False),
        sa.Column('purpose', sa.String(), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('used_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_otp_codes_user_id', 'otp_codes', ['user_id'])
    op.create_index('idx_otp_codes_code_hash', 'otp_codes', ['code_hash'])
    op.create_index('idx_otp_codes_purpose', 'otp_codes', ['purpose'])
    op.create_index('idx_otp_codes_expires_at', 'otp_codes', ['expires_at'])

    # Product Plans table
    op.create_table(
        'product_plans',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('features', postgresql.JSONB(), server_default='{}'),
        sa.Column('limits', postgresql.JSONB(), server_default='{}'),
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='product_plans_slug_key')
    )
    op.create_index('idx_product_plans_slug', 'product_plans', ['slug'])

    # Organization Plans table
    op.create_table(
        'organization_plans',
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('plan_id', sa.String(), nullable=False),
        sa.Column('starts_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('ends_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('status', sa.String(), server_default='active'),
        sa.PrimaryKeyConstraint('organization_id', 'plan_id', 'starts_at'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['product_plans.id'], ondelete='CASCADE')
    )
    op.create_index('idx_organization_plans_organization_id', 'organization_plans', ['organization_id'])
    op.create_index('idx_organization_plans_plan_id', 'organization_plans', ['plan_id'])
    op.create_index('idx_organization_plans_status', 'organization_plans', ['status'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('organization_plans')
    op.drop_table('product_plans')
    op.drop_table('otp_codes')
    op.drop_table('sessions')
    op.drop_table('api_keys')
    op.drop_table('user_permissions')
    op.drop_table('group_permissions')
    op.drop_table('permissions')
    op.drop_table('user_groups')
    op.drop_table('groups')
    op.drop_table('users')
    op.drop_table('organizations')
