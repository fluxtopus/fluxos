"""Create automations table.

Revision ID: automations_001
Revises: inbox_001
Create Date: 2026-01-30 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "automations_001"
down_revision = "inbox_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(255), nullable=True),
        sa.Column("cron", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("idx_automation_owner", "automations", ["owner_id"])
    op.create_index("idx_automation_org", "automations", ["organization_id"])
    op.create_index("idx_automation_task", "automations", ["task_id"])
    op.create_index("idx_automation_poll", "automations", ["enabled", "next_run_at"])


def downgrade() -> None:
    op.drop_index("idx_automation_poll", table_name="automations")
    op.drop_index("idx_automation_task", table_name="automations")
    op.drop_index("idx_automation_org", table_name="automations")
    op.drop_index("idx_automation_owner", table_name="automations")
    op.drop_table("automations")
