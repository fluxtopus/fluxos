"""Add integration webhook events and deliveries tables for INT-012.

INT-012: Event Routing - Track integration webhook events and their delivery status.

Revision ID: 005
Revises: 004
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for event status (IF NOT EXISTS for idempotency)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'integration_webhook_event_status_enum') THEN
                CREATE TYPE integration_webhook_event_status_enum AS ENUM (
                    'received', 'routing', 'delivered', 'failed'
                );
            END IF;
        END$$;
    """)

    # Create integration_webhook_events table
    op.create_table(
        'integration_webhook_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('integration_id', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(50), nullable=False),
        sa.Column('webhook_path', sa.String(100), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('transformed_payload', sa.JSON(), nullable=True),
        sa.Column('destination_service', sa.String(50), nullable=False),
        sa.Column('destination_config', sa.JSON(), nullable=True),
        sa.Column('status', postgresql.ENUM('received', 'routing', 'delivered', 'failed',
                                             name='integration_webhook_event_status_enum', create_type=False),
                  nullable=False, server_default='received'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integration_webhook_events_integration_id', 'integration_webhook_events', ['integration_id'])
    op.create_index('ix_integration_webhook_events_organization_id', 'integration_webhook_events', ['organization_id'])
    op.create_index('ix_integration_webhook_events_webhook_path', 'integration_webhook_events', ['webhook_path'])
    op.create_index('ix_integration_webhook_events_provider', 'integration_webhook_events', ['provider'])
    op.create_index('ix_integration_webhook_events_event_type', 'integration_webhook_events', ['event_type'])
    op.create_index('ix_integration_webhook_events_status', 'integration_webhook_events', ['status'])
    op.create_index('ix_integration_webhook_events_org_created', 'integration_webhook_events', ['organization_id', 'created_at'])

    # Create integration_webhook_deliveries table
    op.create_table(
        'integration_webhook_deliveries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('destination_service', sa.String(50), nullable=False),
        sa.Column('destination_url', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('celery_task_id', sa.String(255), nullable=True),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempt_count', sa.Integer(), server_default='1'),
        sa.Column('last_attempt_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['event_id'], ['integration_webhook_events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integration_webhook_deliveries_event_id', 'integration_webhook_deliveries', ['event_id'])


def downgrade() -> None:
    op.drop_index('ix_integration_webhook_deliveries_event_id', 'integration_webhook_deliveries')
    op.drop_table('integration_webhook_deliveries')

    op.drop_index('ix_integration_webhook_events_org_created', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_status', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_event_type', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_provider', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_webhook_path', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_organization_id', 'integration_webhook_events')
    op.drop_index('ix_integration_webhook_events_integration_id', 'integration_webhook_events')
    op.drop_table('integration_webhook_events')

    op.execute('DROP TYPE integration_webhook_event_status_enum')
