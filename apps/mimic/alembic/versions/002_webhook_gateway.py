"""Webhook gateway tables

Revision ID: 002_webhook_gateway
Revises: 001_initial
Create Date: 2025-01-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_webhook_gateway'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Webhook events table - logs all inbound webhooks from external services
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),  # stripe, resend, etc.
        sa.Column('event_type', sa.String(100), nullable=False),  # checkout.session.completed
        sa.Column('event_id', sa.String(255), nullable=False),  # Provider's event ID
        sa.Column('payload', sa.JSON(), nullable=False),  # Raw payload
        sa.Column('signature', sa.String(500), nullable=True),  # For verification audit
        sa.Column('status', sa.String(20), server_default='received'),  # received, processing, delivered, failed
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_webhook_events_provider', 'webhook_events', ['provider'])
    op.create_index('idx_webhook_events_event_type', 'webhook_events', ['event_type'])
    op.create_index('idx_webhook_events_status', 'webhook_events', ['status'])
    op.create_index('idx_webhook_events_created', 'webhook_events', ['created_at'])
    # Unique constraint for idempotency
    op.create_index('idx_webhook_events_provider_event_id', 'webhook_events', ['provider', 'event_id'], unique=True)

    # Webhook deliveries table - tracks routing to downstream services
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('target_service', sa.String(50), nullable=False),  # inkpass, tentackl, custom, etc.
        sa.Column('task_name', sa.String(255), nullable=False),  # Celery task name
        sa.Column('status', sa.String(20), server_default='pending'),  # pending, success, failed
        sa.Column('celery_task_id', sa.String(255), nullable=True),  # Celery task ID
        sa.Column('result', sa.JSON(), nullable=True),  # Task result or error details
        sa.Column('attempt_count', sa.Integer(), server_default='0'),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['event_id'], ['webhook_events.id'], ondelete='CASCADE')
    )
    op.create_index('idx_webhook_deliveries_event_id', 'webhook_deliveries', ['event_id'])
    op.create_index('idx_webhook_deliveries_status', 'webhook_deliveries', ['status'])


def downgrade() -> None:
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_events')
