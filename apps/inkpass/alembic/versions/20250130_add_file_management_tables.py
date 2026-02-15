"""Add file management tables

Revision ID: 20250130_files
Revises: 866ca41b19ce
Create Date: 2025-01-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20250130_files'
down_revision: Union[str, None] = '866ca41b19ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add storage quota columns to organizations
    op.add_column('organizations', sa.Column('storage_quota_bytes', sa.BigInteger(), server_default='5368709120', nullable=True))
    op.add_column('organizations', sa.Column('storage_used_bytes', sa.BigInteger(), server_default='0', nullable=True))

    # Create files table
    op.create_table(
        'files',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('content_type', sa.String(127), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=True),
        sa.Column('folder_path', sa.String(1024), server_default='/'),
        sa.Column('tags', postgresql.JSONB(), server_default='[]'),
        sa.Column('custom_metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_by_user_id', sa.String(), nullable=True),
        sa.Column('created_by_agent', sa.String(127), nullable=True),
        sa.Column('workflow_id', sa.String(127), nullable=True),
        sa.Column('status', sa.String(31), server_default='active'),
        sa.Column('is_temporary', sa.Boolean(), server_default='false'),
        sa.Column('is_public', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_key'),
        sa.UniqueConstraint('organization_id', 'folder_path', 'name', name='files_org_folder_name_unique'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL')
    )

    # Create indexes for files table
    op.create_index('idx_files_org_id', 'files', ['organization_id'])
    op.create_index('idx_files_folder_path', 'files', ['organization_id', 'folder_path'])
    op.create_index('idx_files_workflow_id', 'files', ['workflow_id'], postgresql_where=sa.text("workflow_id IS NOT NULL"))
    op.create_index('idx_files_status', 'files', ['status'])
    op.create_index('idx_files_tags', 'files', ['tags'], postgresql_using='gin')
    op.create_index('idx_files_expires_at', 'files', ['expires_at'], postgresql_where=sa.text("expires_at IS NOT NULL"))

    # Create file_access_logs table
    op.create_table(
        'file_access_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(31), nullable=False),
        sa.Column('accessor_type', sa.String(31), nullable=False),
        sa.Column('accessor_id', sa.String(127), nullable=False),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE')
    )

    # Create indexes for file_access_logs
    op.create_index('idx_file_access_logs_file_id', 'file_access_logs', ['file_id'])
    op.create_index('idx_file_access_logs_created_at', 'file_access_logs', ['created_at'])


def downgrade() -> None:
    # Drop file_access_logs table
    op.drop_index('idx_file_access_logs_created_at', table_name='file_access_logs')
    op.drop_index('idx_file_access_logs_file_id', table_name='file_access_logs')
    op.drop_table('file_access_logs')

    # Drop files table
    op.drop_index('idx_files_expires_at', table_name='files')
    op.drop_index('idx_files_tags', table_name='files')
    op.drop_index('idx_files_status', table_name='files')
    op.drop_index('idx_files_workflow_id', table_name='files')
    op.drop_index('idx_files_folder_path', table_name='files')
    op.drop_index('idx_files_org_id', table_name='files')
    op.drop_table('files')

    # Remove storage columns from organizations
    op.drop_column('organizations', 'storage_used_bytes')
    op.drop_column('organizations', 'storage_quota_bytes')
