"""Add billing schema

Revision ID: 20260111_billing
Revises: 20260103_embedding
Create Date: 2026-01-11

Adds billing fields to organizations table and creates billing_configs table
for storing encrypted Stripe credentials.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260111_billing'
down_revision = '20260103_embedding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add billing fields to organizations table
    op.add_column('organizations', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('subscription_status', sa.String(50), server_default='none', nullable=True))
    op.add_column('organizations', sa.Column('subscription_tier', sa.String(50), server_default='free', nullable=True))
    op.add_column('organizations', sa.Column('subscription_id', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('subscription_ends_at', sa.TIMESTAMP(), nullable=True))

    # Create billing_configs table
    op.create_table(
        'billing_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('stripe_api_key_encrypted', sa.Text(), nullable=False),
        sa.Column('stripe_webhook_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('price_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id')
    )

    # Create index for faster lookups
    op.create_index('ix_billing_configs_organization_id', 'billing_configs', ['organization_id'])
    op.create_index('ix_organizations_stripe_customer_id', 'organizations', ['stripe_customer_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_organizations_stripe_customer_id', table_name='organizations')
    op.drop_index('ix_billing_configs_organization_id', table_name='billing_configs')

    # Drop billing_configs table
    op.drop_table('billing_configs')

    # Remove billing fields from organizations table
    op.drop_column('organizations', 'subscription_ends_at')
    op.drop_column('organizations', 'subscription_id')
    op.drop_column('organizations', 'subscription_tier')
    op.drop_column('organizations', 'subscription_status')
    op.drop_column('organizations', 'stripe_customer_id')
