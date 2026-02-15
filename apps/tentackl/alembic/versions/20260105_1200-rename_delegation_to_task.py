"""rename_delegation_to_task

Rename "delegation" concept to "task" throughout the database:
- Drop old ticket-like task tables (tasks, task_tags, task_teams, etc.)
- Rename delegation_plans -> tasks
- Rename delegation_plan_events -> task_events
- Update FK column names (plan_id -> task_id)

This is a BREAKING change - no backward compatibility.

Revision ID: f1a2b3c4d5e6
Revises: e0b2bd83ea1b
Create Date: 2026-01-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e0b2bd83ea1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # STEP 1: Remove FK constraints from delegation_plans that reference old tasks
    # ==========================================================================

    # Drop the task_id FK from delegation_plans (references old tasks table)
    op.drop_index("idx_delegation_plan_task", "delegation_plans")
    op.drop_constraint("fk_delegation_plan_task", "delegation_plans", type_="foreignkey")
    op.drop_column("delegation_plans", "task_id")

    # Drop the task_id FK from checkpoint_approvals (references old tasks table)
    op.drop_index("idx_checkpoint_task", "checkpoint_approvals")
    op.drop_constraint("fk_checkpoint_task", "checkpoint_approvals", type_="foreignkey")
    op.drop_column("checkpoint_approvals", "task_context")
    op.drop_column("checkpoint_approvals", "task_id")

    # ==========================================================================
    # STEP 2: Drop old task system tables (ticket-like)
    # Order matters due to FK constraints
    # ==========================================================================

    # Drop task_activities (FK to tasks)
    op.drop_index("idx_activity_task_created", "task_activities")
    op.drop_index("idx_activity_created", "task_activities")
    op.drop_index("idx_activity_actor", "task_activities")
    op.drop_index("idx_activity_type", "task_activities")
    op.drop_index("idx_activity_task", "task_activities")
    op.drop_table("task_activities")

    # Drop task_comments (FK to tasks)
    op.drop_index("idx_comment_created", "task_comments")
    op.drop_index("idx_comment_parent", "task_comments")
    op.drop_index("idx_comment_user", "task_comments")
    op.drop_index("idx_comment_task", "task_comments")
    op.drop_table("task_comments")

    # Drop task_tag_assignments (FK to tasks and task_tags)
    op.drop_index("idx_tag_assignment_tag", "task_tag_assignments")
    op.drop_index("idx_tag_assignment_task", "task_tag_assignments")
    op.drop_table("task_tag_assignments")

    # Drop tasks (FK to task_teams, delegation_plans)
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

    # Drop task_tags
    op.drop_index("idx_tag_name", "task_tags")
    op.drop_index("idx_tag_org", "task_tags")
    op.drop_table("task_tags")

    # Drop task_teams
    op.drop_index("idx_team_lead", "task_teams")
    op.drop_index("idx_team_org", "task_teams")
    op.drop_table("task_teams")

    # Drop task_key_sequences
    op.drop_index("idx_key_sequence_org", "task_key_sequences")
    op.drop_table("task_key_sequences")

    # ==========================================================================
    # STEP 3: Rename delegation tables to task tables
    # ==========================================================================

    # Rename delegation_plans -> tasks
    # First, drop all indexes (they'll be recreated with new names)
    op.drop_index("idx_delegation_plan_user", "delegation_plans")
    op.drop_index("idx_delegation_plan_org", "delegation_plans")
    op.drop_index("idx_delegation_plan_status", "delegation_plans")
    op.drop_index("idx_delegation_plan_tree", "delegation_plans")
    op.drop_index("idx_delegation_plan_created", "delegation_plans")
    op.drop_index("idx_delegation_plan_parent", "delegation_plans")
    op.drop_index("idx_delegation_plan_user_status", "delegation_plans")

    # Rename the table
    op.rename_table("delegation_plans", "tasks")

    # Rename the self-referencing FK column
    op.alter_column("tasks", "parent_plan_id", new_column_name="parent_task_id")

    # Update the self-referencing FK constraint
    op.drop_constraint("delegation_plans_parent_plan_id_fkey", "tasks", type_="foreignkey")
    op.create_foreign_key(
        "tasks_parent_task_id_fkey",
        "tasks",
        "tasks",
        ["parent_task_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # Recreate indexes with new names
    op.create_index("idx_task_user", "tasks", ["user_id"])
    op.create_index("idx_task_org", "tasks", ["organization_id"])
    op.create_index("idx_task_status", "tasks", ["status"])
    op.create_index("idx_task_tree", "tasks", ["tree_id"])
    op.create_index("idx_task_created", "tasks", ["created_at"])
    op.create_index("idx_task_parent", "tasks", ["parent_task_id"])
    op.create_index("idx_task_user_status", "tasks", ["user_id", "status"])

    # ==========================================================================
    # STEP 4: Rename delegation_plan_events -> task_events
    # ==========================================================================

    # Drop indexes
    op.drop_index("idx_plan_event_plan", "delegation_plan_events")
    op.drop_index("idx_plan_event_type", "delegation_plan_events")
    op.drop_index("idx_plan_event_created", "delegation_plan_events")
    op.drop_index("idx_plan_event_plan_created", "delegation_plan_events")

    # Drop FK constraint before renaming
    op.drop_constraint("delegation_plan_events_plan_id_fkey", "delegation_plan_events", type_="foreignkey")

    # Rename the table
    op.rename_table("delegation_plan_events", "task_events")

    # Rename plan_id -> task_id
    op.alter_column("task_events", "plan_id", new_column_name="task_id")

    # Recreate FK constraint
    op.create_foreign_key(
        "task_events_task_id_fkey",
        "task_events",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # Recreate indexes
    op.create_index("idx_task_event_task", "task_events", ["task_id"])
    op.create_index("idx_task_event_type", "task_events", ["event_type"])
    op.create_index("idx_task_event_created", "task_events", ["created_at"])
    op.create_index("idx_task_event_task_created", "task_events", ["task_id", "created_at"])

    # ==========================================================================
    # STEP 5: Update checkpoint_approvals FK (plan_id -> task_id)
    # ==========================================================================

    # Drop existing FK and indexes
    op.drop_index("idx_checkpoint_plan", "checkpoint_approvals")
    op.drop_index("idx_checkpoint_plan_step", "checkpoint_approvals")
    op.drop_constraint("checkpoint_approvals_plan_id_fkey", "checkpoint_approvals", type_="foreignkey")

    # Rename column
    op.alter_column("checkpoint_approvals", "plan_id", new_column_name="task_id")

    # Recreate FK constraint
    op.create_foreign_key(
        "checkpoint_approvals_task_id_fkey",
        "checkpoint_approvals",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # Recreate indexes
    op.create_index("idx_checkpoint_task", "checkpoint_approvals", ["task_id"])
    op.create_index("idx_checkpoint_task_step", "checkpoint_approvals", ["task_id", "step_id"])

    # ==========================================================================
    # STEP 6: Update observer_reports FK (plan_id -> task_id)
    # ==========================================================================

    # Drop existing FK and index
    op.drop_index("idx_observer_plan", "observer_reports")
    op.drop_constraint("observer_reports_plan_id_fkey", "observer_reports", type_="foreignkey")

    # Rename column
    op.alter_column("observer_reports", "plan_id", new_column_name="task_id")

    # Recreate FK constraint
    op.create_foreign_key(
        "observer_reports_task_id_fkey",
        "observer_reports",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # Recreate index
    op.create_index("idx_observer_task", "observer_reports", ["task_id"])


def downgrade() -> None:
    # This is a BREAKING migration - downgrade is complex and not recommended
    # It would require recreating all the dropped tables and data
    raise NotImplementedError(
        "Downgrade not supported for this migration. "
        "This is a breaking change that drops the old task system. "
        "Restore from backup if needed."
    )
