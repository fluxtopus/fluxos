"""add_task_management_tables

Add tables for task management system:
- tasks: Long-lived work items (like Jira/Linear tickets)
- task_tags: User-defined flat labels for categorization
- task_teams: Teams for grouping tasks and ownership
- task_tag_assignments: Many-to-many relationship for task tags
- task_comments: Comments for collaboration
- task_activities: Audit trail of task changes
- task_key_sequences: Atomic key generation per organization

Also adds task_id columns to delegation_plans and checkpoint_approvals
for task-plan integration.

Revision ID: e0b2bd83ea1b
Revises: b8ae412ddb97
Create Date: 2026-01-03 22:33:39.317051

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e0b2bd83ea1b"
down_revision = "b8ae412ddb97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create task_teams table first (referenced by tasks)
    op.create_table(
        "task_teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lead_user_id", sa.String(255), nullable=True),
        sa.Column("member_ids", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uix_team_org_name"),
    )

    # Create indexes for task_teams
    op.create_index("idx_team_org", "task_teams", ["organization_id"])
    op.create_index("idx_team_lead", "task_teams", ["lead_user_id"])

    # Create task_tags table
    op.create_table(
        "task_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),  # Hex color code
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uix_tag_org_name"),
    )

    # Create indexes for task_tags
    op.create_index("idx_tag_org", "task_tags", ["organization_id"])
    op.create_index("idx_tag_name", "task_tags", ["name"])

    # Create task_key_sequences table
    op.create_table(
        "task_key_sequences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False, unique=True),
        sa.Column("prefix", sa.String(20), nullable=False, server_default="TASK"),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create index for task_key_sequences
    op.create_index("idx_key_sequence_org", "task_key_sequences", ["organization_id"])

    # Create tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),  # Human-readable key
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assignee_type", sa.String(50), nullable=True),
        sa.Column("assignee_id", sa.String(255), nullable=True),
        sa.Column("delegation_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_tree_id", sa.String(255), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("estimated_hours", sa.Float(), nullable=True),
        sa.Column("progress_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("attachments", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("extra_metadata", postgresql.JSON(), nullable=True, server_default="{}"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["task_teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["delegation_plan_id"], ["delegation_plans.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "key", name="uix_task_org_key"),
    )

    # Create indexes for tasks
    op.create_index("idx_task_org", "tasks", ["organization_id"])
    op.create_index("idx_task_status", "tasks", ["status"])
    op.create_index("idx_task_priority", "tasks", ["priority"])
    op.create_index("idx_task_parent", "tasks", ["parent_task_id"])
    op.create_index("idx_task_team", "tasks", ["team_id"])
    op.create_index("idx_task_assignee", "tasks", ["assignee_type", "assignee_id"])
    op.create_index("idx_task_delegation_plan", "tasks", ["delegation_plan_id"])
    op.create_index("idx_task_due_date", "tasks", ["due_date"])
    op.create_index("idx_task_created_at", "tasks", ["created_at"])
    op.create_index("idx_task_org_status", "tasks", ["organization_id", "status"])
    op.create_index("idx_task_org_assignee", "tasks", ["organization_id", "assignee_type", "assignee_id"])
    op.create_index("idx_task_org_team", "tasks", ["organization_id", "team_id"])

    # Create task_tag_assignments association table
    op.create_table(
        "task_tag_assignments",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["task_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )

    # Create indexes for task_tag_assignments
    op.create_index("idx_tag_assignment_task", "task_tag_assignments", ["task_id"])
    op.create_index("idx_tag_assignment_tag", "task_tag_assignments", ["tag_id"])

    # Create task_comments table
    op.create_table(
        "task_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parent_comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_comment_id"], ["task_comments.id"], ondelete="CASCADE"),
    )

    # Create indexes for task_comments
    op.create_index("idx_comment_task", "task_comments", ["task_id"])
    op.create_index("idx_comment_user", "task_comments", ["user_id"])
    op.create_index("idx_comment_parent", "task_comments", ["parent_comment_id"])
    op.create_index("idx_comment_created", "task_comments", ["created_at"])

    # Create task_activities table
    op.create_table(
        "task_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("actor_type", sa.String(50), nullable=False, server_default="user"),
        sa.Column("old_value", postgresql.JSON(), nullable=True),
        sa.Column("new_value", postgresql.JSON(), nullable=True),
        sa.Column("details", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
    )

    # Create indexes for task_activities
    op.create_index("idx_activity_task", "task_activities", ["task_id"])
    op.create_index("idx_activity_type", "task_activities", ["activity_type"])
    op.create_index("idx_activity_actor", "task_activities", ["actor_type", "actor_id"])
    op.create_index("idx_activity_created", "task_activities", ["created_at"])
    op.create_index("idx_activity_task_created", "task_activities", ["task_id", "created_at"])

    # Add task_id column to delegation_plans for bidirectional task-plan link
    op.add_column(
        "delegation_plans",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_delegation_plan_task",
        "delegation_plans",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL"
    )
    op.create_index("idx_delegation_plan_task", "delegation_plans", ["task_id"])

    # Add task_id and task_context columns to checkpoint_approvals for task routing
    op.add_column(
        "checkpoint_approvals",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "checkpoint_approvals",
        sa.Column("task_context", postgresql.JSON(), nullable=True)
    )
    op.create_foreign_key(
        "fk_checkpoint_task",
        "checkpoint_approvals",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL"
    )
    op.create_index("idx_checkpoint_task", "checkpoint_approvals", ["task_id"])


def downgrade() -> None:
    # Drop task_id from checkpoint_approvals
    op.drop_index("idx_checkpoint_task", "checkpoint_approvals")
    op.drop_constraint("fk_checkpoint_task", "checkpoint_approvals", type_="foreignkey")
    op.drop_column("checkpoint_approvals", "task_context")
    op.drop_column("checkpoint_approvals", "task_id")

    # Drop task_id from delegation_plans
    op.drop_index("idx_delegation_plan_task", "delegation_plans")
    op.drop_constraint("fk_delegation_plan_task", "delegation_plans", type_="foreignkey")
    op.drop_column("delegation_plans", "task_id")

    # Drop task_activities
    op.drop_index("idx_activity_task_created", "task_activities")
    op.drop_index("idx_activity_created", "task_activities")
    op.drop_index("idx_activity_actor", "task_activities")
    op.drop_index("idx_activity_type", "task_activities")
    op.drop_index("idx_activity_task", "task_activities")
    op.drop_table("task_activities")

    # Drop task_comments
    op.drop_index("idx_comment_created", "task_comments")
    op.drop_index("idx_comment_parent", "task_comments")
    op.drop_index("idx_comment_user", "task_comments")
    op.drop_index("idx_comment_task", "task_comments")
    op.drop_table("task_comments")

    # Drop task_tag_assignments
    op.drop_index("idx_tag_assignment_tag", "task_tag_assignments")
    op.drop_index("idx_tag_assignment_task", "task_tag_assignments")
    op.drop_table("task_tag_assignments")

    # Drop tasks
    op.drop_index("idx_task_org_team", "tasks")
    op.drop_index("idx_task_org_assignee", "tasks")
    op.drop_index("idx_task_org_status", "tasks")
    op.drop_index("idx_task_created_at", "tasks")
    op.drop_index("idx_task_due_date", "tasks")
    op.drop_index("idx_task_delegation_plan", "tasks")
    op.drop_index("idx_task_assignee", "tasks")
    op.drop_index("idx_task_team", "tasks")
    op.drop_index("idx_task_parent", "tasks")
    op.drop_index("idx_task_priority", "tasks")
    op.drop_index("idx_task_status", "tasks")
    op.drop_index("idx_task_org", "tasks")
    op.drop_table("tasks")

    # Drop task_key_sequences
    op.drop_index("idx_key_sequence_org", "task_key_sequences")
    op.drop_table("task_key_sequences")

    # Drop task_tags
    op.drop_index("idx_tag_name", "task_tags")
    op.drop_index("idx_tag_org", "task_tags")
    op.drop_table("task_tags")

    # Drop task_teams
    op.drop_index("idx_team_lead", "task_teams")
    op.drop_index("idx_team_org", "task_teams")
    op.drop_table("task_teams")
