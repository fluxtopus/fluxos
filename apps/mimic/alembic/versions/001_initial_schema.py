"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('subscription_tier', sa.String(), server_default='free'),
        sa.Column('subscription_expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_users_email', 'users', ['email'], unique=True)
    
    # API keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('idx_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)
    
    # Workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('definition_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_workflows_user_id', 'workflows', ['user_id'])
    op.create_index('idx_workflows_is_active', 'workflows', ['is_active'])
    
    # Provider keys table
    op.create_table(
        'provider_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('provider_type', sa.String(), nullable=False),
        sa.Column('encrypted_api_key', sa.Text(), nullable=True),
        sa.Column('encrypted_secret', sa.Text(), nullable=True),
        sa.Column('webhook_url', sa.String(), nullable=True),
        sa.Column('bot_token', sa.Text(), nullable=True),
        sa.Column('from_email', sa.String(), nullable=True),
        sa.Column('from_number', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'provider_type')
    )
    op.create_index('idx_provider_keys_user_id', 'provider_keys', ['user_id'])
    op.create_index('idx_provider_keys_provider_type', 'provider_keys', ['provider_type'])
    op.create_index('idx_provider_keys_is_active', 'provider_keys', ['is_active'])
    
    # Templates table
    op.create_table(
        'templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('variables', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_templates_user_id', 'templates', ['user_id'])
    
    # Delivery logs table
    op.create_table(
        'delivery_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('delivery_id', sa.String(), nullable=False),
        sa.Column('workflow_id', sa.String(), nullable=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('recipient', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('provider_cost', sa.Numeric(10, 4), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'])
    )
    op.create_index('idx_delivery_logs_user_id', 'delivery_logs', ['user_id'])
    op.create_index('idx_delivery_logs_delivery_id', 'delivery_logs', ['delivery_id'], unique=True)
    op.create_index('idx_delivery_logs_workflow_id', 'delivery_logs', ['workflow_id'])
    op.create_index('idx_delivery_logs_status', 'delivery_logs', ['status'])
    op.create_index('idx_delivery_logs_created_at', 'delivery_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_delivery_logs_created_at', table_name='delivery_logs')
    op.drop_index('idx_delivery_logs_status', table_name='delivery_logs')
    op.drop_index('idx_delivery_logs_workflow_id', table_name='delivery_logs')
    op.drop_index('idx_delivery_logs_delivery_id', table_name='delivery_logs')
    op.drop_index('idx_delivery_logs_user_id', table_name='delivery_logs')
    op.drop_table('delivery_logs')
    
    op.drop_index('idx_templates_user_id', table_name='templates')
    op.drop_table('templates')
    
    op.drop_index('idx_provider_keys_is_active', table_name='provider_keys')
    op.drop_index('idx_provider_keys_provider_type', table_name='provider_keys')
    op.drop_index('idx_provider_keys_user_id', table_name='provider_keys')
    op.drop_table('provider_keys')
    
    op.drop_index('idx_workflows_is_active', table_name='workflows')
    op.drop_index('idx_workflows_user_id', table_name='workflows')
    op.drop_table('workflows')
    
    op.drop_index('idx_api_keys_key_hash', table_name='api_keys')
    op.drop_index('idx_api_keys_user_id', table_name='api_keys')
    op.drop_table('api_keys')
    
    op.drop_index('idx_users_email', table_name='users')
    op.drop_table('users')

