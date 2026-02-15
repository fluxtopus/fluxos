"""add_delegation_tables

Add tables for autonomous task delegation:
- delegation_plans: Persistent plan documents
- user_preferences: Learned approval preferences
- checkpoint_approvals: Approval history
- delegation_plan_events: Audit trail
- observer_reports: Observer agent reports

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2025-12-28 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "aa9c7be64c84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create delegation_plans table
    op.create_table(
        "delegation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(255), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("constraints", postgresql.JSON(), nullable=True, server_default="{}"),
        sa.Column("success_criteria", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("steps", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("accumulated_findings", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="planning"),
        sa.Column("tree_id", sa.String(255), nullable=True),
        sa.Column("parent_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", postgresql.JSON(), nullable=True, server_default="{}"),
        sa.Column("source", sa.String(50), nullable=True, server_default="api"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["parent_plan_id"], ["delegation_plans.id"], ondelete="SET NULL"),
    )

    # Create indexes for delegation_plans
    op.create_index("idx_delegation_plan_user", "delegation_plans", ["user_id"])
    op.create_index("idx_delegation_plan_org", "delegation_plans", ["organization_id"])
    op.create_index("idx_delegation_plan_status", "delegation_plans", ["status"])
    op.create_index("idx_delegation_plan_tree", "delegation_plans", ["tree_id"])
    op.create_index("idx_delegation_plan_created", "delegation_plans", ["created_at"])
    op.create_index("idx_delegation_plan_parent", "delegation_plans", ["parent_plan_id"])
    op.create_index("idx_delegation_plan_user_status", "delegation_plans", ["user_id", "status"])

    # Create user_preferences table
    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(255), nullable=True),
        sa.Column("preference_key", sa.String(255), nullable=False),
        sa.Column("pattern", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSON(), nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for user_preferences
    op.create_index("idx_pref_user", "user_preferences", ["user_id"])
    op.create_index("idx_pref_user_key", "user_preferences", ["user_id", "preference_key"])
    op.create_index("idx_pref_org", "user_preferences", ["organization_id"])
    op.create_index("idx_pref_confidence", "user_preferences", ["confidence"])
    op.create_index("idx_pref_last_used", "user_preferences", ["last_used"])
    op.create_index("idx_pref_decision", "user_preferences", ["decision"])

    # Create checkpoint_approvals table
    op.create_table(
        "checkpoint_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("checkpoint_name", sa.String(255), nullable=False),
        sa.Column("checkpoint_description", sa.Text(), nullable=True),
        sa.Column("preference_key", sa.String(255), nullable=True),
        sa.Column("preview_data", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("preference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("timeout_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["delegation_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preference_id"], ["user_preferences.id"], ondelete="SET NULL"),
    )

    # Create indexes for checkpoint_approvals
    op.create_index("idx_checkpoint_plan", "checkpoint_approvals", ["plan_id"])
    op.create_index("idx_checkpoint_user", "checkpoint_approvals", ["user_id"])
    op.create_index("idx_checkpoint_status", "checkpoint_approvals", ["status"])
    op.create_index("idx_checkpoint_requested", "checkpoint_approvals", ["requested_at"])
    op.create_index("idx_checkpoint_pending", "checkpoint_approvals", ["status", "timeout_at"])
    op.create_index("idx_checkpoint_plan_step", "checkpoint_approvals", ["plan_id", "step_id"])

    # Create delegation_plan_events table
    op.create_table(
        "delegation_plan_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_data", postgresql.JSON(), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["delegation_plans.id"], ondelete="CASCADE"),
    )

    # Create indexes for delegation_plan_events
    op.create_index("idx_plan_event_plan", "delegation_plan_events", ["plan_id"])
    op.create_index("idx_plan_event_type", "delegation_plan_events", ["event_type"])
    op.create_index("idx_plan_event_created", "delegation_plan_events", ["created_at"])
    op.create_index("idx_plan_event_plan_created", "delegation_plan_events", ["plan_id", "created_at"])

    # Create observer_reports table
    op.create_table(
        "observer_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("anomalies", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("proposals", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("recommendation", sa.String(50), nullable=False, server_default="continue"),
        sa.Column("execution_state", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["delegation_plans.id"], ondelete="CASCADE"),
    )

    # Create indexes for observer_reports
    op.create_index("idx_observer_plan", "observer_reports", ["plan_id"])
    op.create_index("idx_observer_recommendation", "observer_reports", ["recommendation"])
    op.create_index("idx_observer_created", "observer_reports", ["created_at"])


def downgrade() -> None:
    # Drop observer_reports
    op.drop_index("idx_observer_created", "observer_reports")
    op.drop_index("idx_observer_recommendation", "observer_reports")
    op.drop_index("idx_observer_plan", "observer_reports")
    op.drop_table("observer_reports")

    # Drop delegation_plan_events
    op.drop_index("idx_plan_event_plan_created", "delegation_plan_events")
    op.drop_index("idx_plan_event_created", "delegation_plan_events")
    op.drop_index("idx_plan_event_type", "delegation_plan_events")
    op.drop_index("idx_plan_event_plan", "delegation_plan_events")
    op.drop_table("delegation_plan_events")

    # Drop checkpoint_approvals
    op.drop_index("idx_checkpoint_plan_step", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_pending", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_requested", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_status", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_user", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_plan", "checkpoint_approvals")
    op.drop_table("checkpoint_approvals")

    # Drop user_preferences
    op.drop_index("idx_pref_decision", "user_preferences")
    op.drop_index("idx_pref_last_used", "user_preferences")
    op.drop_index("idx_pref_confidence", "user_preferences")
    op.drop_index("idx_pref_org", "user_preferences")
    op.drop_index("idx_pref_user_key", "user_preferences")
    op.drop_index("idx_pref_user", "user_preferences")
    op.drop_table("user_preferences")

    # Drop delegation_plans
    op.drop_index("idx_delegation_plan_user_status", "delegation_plans")
    op.drop_index("idx_delegation_plan_parent", "delegation_plans")
    op.drop_index("idx_delegation_plan_created", "delegation_plans")
    op.drop_index("idx_delegation_plan_tree", "delegation_plans")
    op.drop_index("idx_delegation_plan_status", "delegation_plans")
    op.drop_index("idx_delegation_plan_org", "delegation_plans")
    op.drop_index("idx_delegation_plan_user", "delegation_plans")
    op.drop_table("delegation_plans")
