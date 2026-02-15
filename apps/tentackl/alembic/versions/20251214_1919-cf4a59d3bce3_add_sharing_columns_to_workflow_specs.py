"""add_sharing_columns_to_workflow_specs

Revision ID: cf4a59d3bce3
Revises: b1c2d3e4f5a6
Create Date: 2025-12-14 19:19:50.943090

Adds columns to enable workflow spec sharing:
- is_public: Makes spec discoverable and runnable by anyone
- owner_id: Links spec to the user who created/owns it
- copied_from_id: References the original spec if this is a copy
- copied_from_version: Version of original when copied (for update detection)
- copy_count: Number of times this spec has been copied
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "cf4a59d3bce3"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sharing columns to workflow_specs
    # Step 1: Add is_public as nullable first
    op.add_column(
        "workflow_specs",
        sa.Column("is_public", sa.Boolean(), nullable=True),
    )

    # Step 2: Set default value for existing rows
    op.execute("UPDATE workflow_specs SET is_public = false WHERE is_public IS NULL")

    # Step 3: Now make it non-nullable with server default
    op.alter_column(
        "workflow_specs",
        "is_public",
        nullable=False,
        server_default=sa.text("false")
    )

    op.add_column(
        "workflow_specs", sa.Column("owner_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "workflow_specs", sa.Column("copied_from_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "workflow_specs",
        sa.Column("copied_from_version", sa.String(length=50), nullable=True),
    )
    # copy_count: Track how many times this spec has been copied (for analytics)
    op.add_column(
        "workflow_specs",
        sa.Column("copy_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_wf_spec_public", "workflow_specs", ["is_public"], unique=False
    )
    op.create_index(
        "idx_wf_spec_owner", "workflow_specs", ["owner_id"], unique=False
    )
    op.create_index(
        "idx_wf_spec_copied_from", "workflow_specs", ["copied_from_id"], unique=False
    )
    # Composite index for public spec queries (WHERE is_public = true AND is_active = true)
    op.create_index(
        "idx_wf_spec_public_active", "workflow_specs", ["is_public", "is_active"], unique=False
    )

    # Create self-referential foreign key for copied_from
    op.create_foreign_key(
        "fk_workflow_specs_copied_from",
        "workflow_specs",
        "workflow_specs",
        ["copied_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint(
        "fk_workflow_specs_copied_from", "workflow_specs", type_="foreignkey"
    )

    # Drop indexes
    op.drop_index("idx_wf_spec_public_active", table_name="workflow_specs")
    op.drop_index("idx_wf_spec_copied_from", table_name="workflow_specs")
    op.drop_index("idx_wf_spec_owner", table_name="workflow_specs")
    op.drop_index("idx_wf_spec_public", table_name="workflow_specs")

    # Drop columns
    op.drop_column("workflow_specs", "copy_count")
    op.drop_column("workflow_specs", "copied_from_version")
    op.drop_column("workflow_specs", "copied_from_id")
    op.drop_column("workflow_specs", "owner_id")
    op.drop_column("workflow_specs", "is_public")
