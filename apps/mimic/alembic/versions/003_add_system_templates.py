"""Add system_templates table for org-scoped transactional email templates.

Revision ID: 003
Revises: 002_webhook_gateway
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002_webhook_gateway'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'system_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('content_html', sa.Text(), nullable=True),
        sa.Column('variables', sa.JSON(), default=list),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('ix_system_templates_organization_id', 'system_templates', ['organization_id'])
    op.create_index('ix_system_templates_name', 'system_templates', ['name'])

    # Unique constraint: one template per name per org (null org = platform template)
    op.create_index(
        'ix_system_templates_org_name',
        'system_templates',
        ['organization_id', 'name'],
        unique=True,
        postgresql_where=sa.text('organization_id IS NOT NULL')
    )


def downgrade() -> None:
    op.drop_index('ix_system_templates_org_name', 'system_templates')
    op.drop_index('ix_system_templates_name', 'system_templates')
    op.drop_index('ix_system_templates_organization_id', 'system_templates')
    op.drop_table('system_templates')
