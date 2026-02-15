"""Add integration system tables for centralized integration management.

INT-001: Integration model
INT-002: IntegrationCredential model
INT-003: IntegrationInboundConfig model
INT-004: IntegrationOutboundConfig model

Revision ID: 004
Revises: 003
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types first
    op.execute("""
        CREATE TYPE integration_provider_enum AS ENUM (
            'discord', 'slack', 'github', 'stripe', 'custom_webhook'
        )
    """)
    op.execute("""
        CREATE TYPE integration_direction_enum AS ENUM (
            'inbound', 'outbound', 'bidirectional'
        )
    """)
    op.execute("""
        CREATE TYPE integration_status_enum AS ENUM (
            'active', 'paused', 'error'
        )
    """)
    op.execute("""
        CREATE TYPE credential_type_enum AS ENUM (
            'api_key', 'oauth_token', 'webhook_url', 'bot_token', 'webhook_secret'
        )
    """)
    op.execute("""
        CREATE TYPE inbound_auth_method_enum AS ENUM (
            'api_key', 'signature', 'bearer', 'none'
        )
    """)
    op.execute("""
        CREATE TYPE destination_service_enum AS ENUM (
            'tentackl', 'custom'
        )
    """)
    op.execute("""
        CREATE TYPE outbound_action_type_enum AS ENUM (
            'send_message', 'send_embed', 'send_blocks', 'create_issue',
            'post_comment', 'post', 'put'
        )
    """)

    # INT-001: Integration table
    op.create_table(
        'integrations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('provider', postgresql.ENUM('discord', 'slack', 'github', 'stripe', 'custom_webhook',
                                               name='integration_provider_enum', create_type=False), nullable=False),
        sa.Column('direction', postgresql.ENUM('inbound', 'outbound', 'bidirectional',
                                                name='integration_direction_enum', create_type=False),
                  nullable=False, server_default='bidirectional'),
        sa.Column('status', postgresql.ENUM('active', 'paused', 'error',
                                             name='integration_status_enum', create_type=False),
                  nullable=False, server_default='active'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integrations_organization_id', 'integrations', ['organization_id'])
    op.create_index('ix_integrations_user_id', 'integrations', ['user_id'])
    op.create_index('ix_integrations_provider', 'integrations', ['provider'])
    op.create_index('ix_integrations_status', 'integrations', ['status'])
    op.create_index('ix_integrations_org_provider', 'integrations', ['organization_id', 'provider'])
    op.create_index('ix_integrations_org_status', 'integrations', ['organization_id', 'status'])

    # INT-002: IntegrationCredential table
    op.create_table(
        'integration_credentials',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('integration_id', sa.String(), nullable=False),
        sa.Column('credential_type', postgresql.ENUM('api_key', 'oauth_token', 'webhook_url', 'bot_token', 'webhook_secret',
                                                      name='credential_type_enum', create_type=False), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('credential_metadata', sa.JSON(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integration_credentials_integration_id', 'integration_credentials', ['integration_id'])
    op.create_index('ix_integration_credentials_type', 'integration_credentials', ['integration_id', 'credential_type'])

    # INT-003: IntegrationInboundConfig table
    op.create_table(
        'integration_inbound_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('integration_id', sa.String(), nullable=False),
        sa.Column('webhook_path', sa.String(100), nullable=False),
        sa.Column('auth_method', postgresql.ENUM('api_key', 'signature', 'bearer', 'none',
                                                  name='inbound_auth_method_enum', create_type=False),
                  nullable=False, server_default='none'),
        sa.Column('signature_secret', sa.Text(), nullable=True),
        sa.Column('event_filters', sa.JSON(), nullable=True),
        sa.Column('transform_template', sa.Text(), nullable=True),
        sa.Column('destination_service', postgresql.ENUM('tentackl', 'custom',
                                                          name='destination_service_enum', create_type=False),
                  nullable=False, server_default='tentackl'),
        sa.Column('destination_config', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('integration_id'),
        sa.UniqueConstraint('webhook_path'),
    )
    op.create_index('ix_integration_inbound_configs_webhook_path', 'integration_inbound_configs', ['webhook_path'])

    # INT-004: IntegrationOutboundConfig table
    op.create_table(
        'integration_outbound_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('integration_id', sa.String(), nullable=False),
        sa.Column('action_type', postgresql.ENUM('send_message', 'send_embed', 'send_blocks', 'create_issue',
                                                   'post_comment', 'post', 'put',
                                                   name='outbound_action_type_enum', create_type=False), nullable=False),
        sa.Column('default_template', sa.JSON(), nullable=True),
        sa.Column('rate_limit_requests', sa.Integer(), nullable=True),
        sa.Column('rate_limit_window_seconds', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('integration_id'),
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table('integration_outbound_configs')
    op.drop_index('ix_integration_inbound_configs_webhook_path', 'integration_inbound_configs')
    op.drop_table('integration_inbound_configs')
    op.drop_index('ix_integration_credentials_type', 'integration_credentials')
    op.drop_index('ix_integration_credentials_integration_id', 'integration_credentials')
    op.drop_table('integration_credentials')
    op.drop_index('ix_integrations_org_status', 'integrations')
    op.drop_index('ix_integrations_org_provider', 'integrations')
    op.drop_index('ix_integrations_status', 'integrations')
    op.drop_index('ix_integrations_provider', 'integrations')
    op.drop_index('ix_integrations_user_id', 'integrations')
    op.drop_index('ix_integrations_organization_id', 'integrations')
    op.drop_table('integrations')

    # Drop enum types
    op.execute('DROP TYPE outbound_action_type_enum')
    op.execute('DROP TYPE destination_service_enum')
    op.execute('DROP TYPE inbound_auth_method_enum')
    op.execute('DROP TYPE credential_type_enum')
    op.execute('DROP TYPE integration_status_enum')
    op.execute('DROP TYPE integration_direction_enum')
    op.execute('DROP TYPE integration_provider_enum')
