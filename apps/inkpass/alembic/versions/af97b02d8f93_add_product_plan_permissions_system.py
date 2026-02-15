"""add_product_plan_permissions_system

Revision ID: af97b02d8f93
Revises: 33ab63e035f7
Create Date: 2025-11-30 04:11:41.869676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af97b02d8f93'
down_revision: Union[str, None] = '33ab63e035f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add product_plan_permissions association table
    op.create_table(
        'product_plan_permissions',
        sa.Column('product_plan_id', sa.String(), nullable=False),
        sa.Column('permission_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_plan_id'], ['product_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('product_plan_id', 'permission_id')
    )

    # Add product_plan_id to users table
    op.add_column('users', sa.Column('product_plan_id', sa.String(), nullable=True))
    op.create_foreign_key('fk_users_product_plan_id', 'users', 'product_plans', ['product_plan_id'], ['id'])
    op.create_index('ix_users_product_plan_id', 'users', ['product_plan_id'])

    # Enhance product_plans table
    op.add_column('product_plans', sa.Column('organization_id', sa.String(), nullable=True))
    op.add_column('product_plans', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('product_plans', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('product_plans', sa.Column('plan_metadata', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('product_plans', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True))

    # Add foreign key for organization_id
    op.create_foreign_key('fk_product_plans_organization_id', 'product_plans', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_product_plans_slug', 'product_plans', ['slug'])

    # Make slug unique per organization (not globally unique)
    op.drop_constraint('product_plans_slug_key', 'product_plans', type_='unique')


def downgrade() -> None:
    # Reverse the changes
    op.drop_index('ix_product_plans_slug', 'product_plans')
    op.drop_constraint('fk_product_plans_organization_id', 'product_plans', type_='foreignkey')
    op.drop_column('product_plans', 'updated_at')
    op.drop_column('product_plans', 'plan_metadata')
    op.drop_column('product_plans', 'is_active')
    op.drop_column('product_plans', 'description')
    op.drop_column('product_plans', 'organization_id')
    op.create_unique_constraint('product_plans_slug_key', 'product_plans', ['slug'])

    op.drop_index('ix_users_product_plan_id', 'users')
    op.drop_constraint('fk_users_product_plan_id', 'users', type_='foreignkey')
    op.drop_column('users', 'product_plan_id')

    op.drop_table('product_plan_permissions')

