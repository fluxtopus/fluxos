"""add_prompt_evaluations_table

Revision ID: d5e6f7a8b9c0
Revises: cf4a59d3bce3
Create Date: 2025-12-22 12:00:00.000000

Adds the prompt_evaluations table for storing LLM-as-judge evaluation results.
This table is used as a CI/CD quality gate before publishing workflow specs or agent versions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "cf4a59d3bce3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create prompt_evaluations table
    op.create_table(
        "prompt_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("prompt_type", sa.String(50), nullable=False),  # system_prompt, agent_prompt, workflow_prompt, general
        sa.Column("prompt_path", sa.String(255), nullable=True),  # e.g., node.analyzer.agent.system_prompt

        # Foreign keys (nullable - evaluation can be standalone or linked to spec/agent)
        sa.Column("workflow_spec_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_spec_id", UUID(as_uuid=True), nullable=True),

        # Evaluation results
        sa.Column("evaluation_result", sa.String(50), nullable=False),  # pass, pass_with_warnings, fail
        sa.Column("overall_score", sa.Integer(), nullable=False),  # Stored as integer (score * 100) for precision
        sa.Column("dimension_scores", JSON, nullable=False),  # {clarity: {score: 4, feedback: "..."}, ...}
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("improvement_suggestions", JSON, nullable=True),  # [{dimension: "...", suggestion: "...", priority: "..."}]

        # Configuration used for evaluation
        sa.Column("threshold", sa.Integer(), nullable=False),  # Stored as integer (threshold * 100) for precision
        sa.Column("model_used", sa.String(100), nullable=True),  # e.g., google/gemini-2.5-flash

        # Override tracking (for admin bypasses)
        sa.Column("override_by", sa.String(255), nullable=True),  # User who overrode the evaluation
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_prompt_eval_workflow_spec", "prompt_evaluations", ["workflow_spec_id"], unique=False
    )
    op.create_index(
        "idx_prompt_eval_agent_spec", "prompt_evaluations", ["agent_spec_id"], unique=False
    )
    op.create_index(
        "idx_prompt_eval_result", "prompt_evaluations", ["evaluation_result"], unique=False
    )
    op.create_index(
        "idx_prompt_eval_type", "prompt_evaluations", ["prompt_type"], unique=False
    )
    op.create_index(
        "idx_prompt_eval_created", "prompt_evaluations", ["created_at"], unique=False
    )
    op.create_index(
        "idx_prompt_eval_score", "prompt_evaluations", ["overall_score"], unique=False
    )

    # Create foreign keys
    op.create_foreign_key(
        "fk_prompt_eval_workflow_spec",
        "prompt_evaluations",
        "workflow_specs",
        ["workflow_spec_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Note: agent_spec_id foreign key will be added when agent_specs table exists
    # For now, we leave it as a UUID without FK constraint since agent registry
    # may use a different storage mechanism


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint(
        "fk_prompt_eval_workflow_spec", "prompt_evaluations", type_="foreignkey"
    )

    # Drop indexes
    op.drop_index("idx_prompt_eval_score", table_name="prompt_evaluations")
    op.drop_index("idx_prompt_eval_created", table_name="prompt_evaluations")
    op.drop_index("idx_prompt_eval_type", table_name="prompt_evaluations")
    op.drop_index("idx_prompt_eval_result", table_name="prompt_evaluations")
    op.drop_index("idx_prompt_eval_agent_spec", table_name="prompt_evaluations")
    op.drop_index("idx_prompt_eval_workflow_spec", table_name="prompt_evaluations")

    # Drop table
    op.drop_table("prompt_evaluations")
