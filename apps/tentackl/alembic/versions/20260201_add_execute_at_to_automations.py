"""Add execute_at column to automations and make cron nullable.

Supports one-time scheduling (execute_at without cron) alongside
recurring cron-based automations.

Revision ID: automations_002
Revises: automations_001
Create Date: 2026-02-01 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "automations_002"
down_revision = "automations_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add execute_at for one-time scheduling
    op.add_column(
        "automations",
        sa.Column("execute_at", sa.DateTime(), nullable=True),
    )

    # Make cron nullable (one-time automations have no cron)
    op.alter_column(
        "automations",
        "cron",
        existing_type=sa.String(255),
        nullable=True,
    )

    # Ensure at least one scheduling method is set
    op.create_check_constraint(
        "ck_automations_schedule_method",
        "automations",
        "cron IS NOT NULL OR execute_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_automations_schedule_method", "automations", type_="check")

    # Set cron to empty string for any one-time automations before making non-null
    op.execute("UPDATE automations SET cron = '' WHERE cron IS NULL")
    op.alter_column(
        "automations",
        "cron",
        existing_type=sa.String(255),
        nullable=False,
    )

    op.drop_column("automations", "execute_at")
