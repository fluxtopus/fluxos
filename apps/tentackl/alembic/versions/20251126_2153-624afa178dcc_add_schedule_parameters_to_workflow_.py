"""add_schedule_parameters_to_workflow_specs

Revision ID: 624afa178dcc
Revises: add_workflow_schedule_fields
Create Date: 2025-11-26 21:53:31.731669

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "624afa178dcc"
down_revision = "add_workflow_schedule_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add schedule_parameters column to workflow_specs table
    op.add_column(
        'workflow_specs',
        sa.Column('schedule_parameters', postgresql.JSON(), nullable=True)
    )


def downgrade() -> None:
    # Drop schedule_parameters column
    op.drop_column('workflow_specs', 'schedule_parameters')
