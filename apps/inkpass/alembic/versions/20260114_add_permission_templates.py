"""Add permission template system

Revision ID: 20260114_templates
Revises: 20260113_backfill_owner
Create Date: 2026-01-14

Adds permission template tables for role-based permission management:
- permission_templates: Global template registry
- role_templates: Roles within a template (owner, admin, developer, viewer)
- role_template_permissions: Permissions granted by each role
- organization_templates: Tracks which template(s) an org uses
- organization_custom_permissions: Tracks source of each permission
- user_organizations.role_template_id: Links users to their role
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260114_templates'
down_revision = '20260113_backfill_owner'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create permission_templates table
    op.create_table(
        'permission_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('product_type', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_permission_templates_product_type', 'permission_templates', ['product_type'])

    # Create role_templates table
    op.create_table(
        'role_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False),
        sa.Column('role_name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('inherits_from', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), server_default='0', nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['permission_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'role_name', name='uq_role_template_name')
    )
    op.create_index('ix_role_templates_template_id', 'role_templates', ['template_id'])

    # Create role_template_permissions table
    op.create_table(
        'role_template_permissions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('role_template_id', sa.String(), nullable=False),
        sa.Column('resource', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['role_template_id'], ['role_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_template_id', 'resource', 'action', name='uq_role_perm')
    )
    op.create_index('ix_role_template_permissions_role_id', 'role_template_permissions', ['role_template_id'])

    # Create organization_templates table
    op.create_table(
        'organization_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False),
        sa.Column('applied_version', sa.Integer(), nullable=False),
        sa.Column('applied_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['permission_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'template_id', name='uq_org_template')
    )
    op.create_index('ix_organization_templates_org_id', 'organization_templates', ['organization_id'])

    # Create organization_custom_permissions table
    op.create_table(
        'organization_custom_permissions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('permission_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='custom'),
        sa.Column('granted_by', sa.String(), nullable=True),
        sa.Column('granted_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'permission_id', name='uq_org_custom_permission')
    )
    op.create_index('ix_org_custom_permissions_org_id', 'organization_custom_permissions', ['organization_id'])
    op.create_index('ix_org_custom_permissions_source', 'organization_custom_permissions', ['source'])

    # Add role_template_id column to user_organizations
    op.add_column(
        'user_organizations',
        sa.Column('role_template_id', sa.String(), nullable=True)
    )
    op.create_foreign_key(
        'fk_user_org_role_template',
        'user_organizations',
        'role_templates',
        ['role_template_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_user_organizations_role_template_id', 'user_organizations', ['role_template_id'])


def downgrade() -> None:
    # Remove role_template_id from user_organizations
    op.drop_index('ix_user_organizations_role_template_id', table_name='user_organizations')
    op.drop_constraint('fk_user_org_role_template', 'user_organizations', type_='foreignkey')
    op.drop_column('user_organizations', 'role_template_id')

    # Drop organization_custom_permissions table
    op.drop_index('ix_org_custom_permissions_source', table_name='organization_custom_permissions')
    op.drop_index('ix_org_custom_permissions_org_id', table_name='organization_custom_permissions')
    op.drop_table('organization_custom_permissions')

    # Drop organization_templates table
    op.drop_index('ix_organization_templates_org_id', table_name='organization_templates')
    op.drop_table('organization_templates')

    # Drop role_template_permissions table
    op.drop_index('ix_role_template_permissions_role_id', table_name='role_template_permissions')
    op.drop_table('role_template_permissions')

    # Drop role_templates table
    op.drop_index('ix_role_templates_template_id', table_name='role_templates')
    op.drop_table('role_templates')

    # Drop permission_templates table
    op.drop_index('ix_permission_templates_product_type', table_name='permission_templates')
    op.drop_table('permission_templates')
