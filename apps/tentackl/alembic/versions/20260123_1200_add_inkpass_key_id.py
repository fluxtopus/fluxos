"""Add inkpass_key_id and drop api_key_hash from external_publishers

Revision ID: 20260123_inkpass
Revises: 20260118_capabilities
Create Date: 2026-01-23

Changes:
- Add inkpass_key_id column for InkPass API key references
- Drop api_key_hash column (replaced by InkPass)
- Update indexes

All webhook integrations now use InkPass for API key management.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260123_inkpass'
down_revision: Union[str, None] = '20260118_capabilities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add inkpass_key_id column
    op.add_column('external_publishers', sa.Column(
        'inkpass_key_id',
        sa.String(255),
        nullable=True,
        unique=True
    ))

    # Create index on inkpass_key_id
    op.create_index(
        'idx_publisher_inkpass_key',
        'external_publishers',
        ['inkpass_key_id'],
        unique=True
    )

    # Drop old api_key_hash index and column
    op.drop_index('idx_publisher_api_key', table_name='external_publishers')
    op.drop_column('external_publishers', 'api_key_hash')

    # Make inkpass_key_id non-nullable now that api_key_hash is gone
    op.alter_column('external_publishers', 'inkpass_key_id',
        existing_type=sa.String(255),
        nullable=False
    )


def downgrade() -> None:
    # Make inkpass_key_id nullable first
    op.alter_column('external_publishers', 'inkpass_key_id',
        existing_type=sa.String(255),
        nullable=True
    )

    # Recreate api_key_hash column
    op.add_column('external_publishers', sa.Column(
        'api_key_hash',
        sa.String(255),
        nullable=True,
        unique=True
    ))

    # Recreate api_key_hash index
    op.create_index(
        'idx_publisher_api_key',
        'external_publishers',
        ['api_key_hash'],
        unique=True
    )

    # Drop inkpass_key_id index and column
    op.drop_index('idx_publisher_inkpass_key', table_name='external_publishers')
    op.drop_column('external_publishers', 'inkpass_key_id')
