"""Add workspace objects tables

Revision ID: 20260112_workspace
Revises: 20260110_memory
Create Date: 2026-01-12

This migration adds the flexible workspace object storage system:

1. workspace_objects: JSONB-based flexible object storage
   - Stores any data type (events, contacts, custom)
   - GIN indexes on data and tags for efficient queries
   - Full-text search via tsvector with auto-update trigger
   - Multi-tenant isolation via org_id

2. workspace_type_schemas: Optional JSON Schema validation
   - Register schemas per type per org
   - Strict mode rejects invalid data, non-strict warns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20260112_workspace'
down_revision: Union[str, None] = '20260110_memory'
# NOTE: This migration was orphaned - the database had been upgraded past this point
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================
    # 1. workspace_objects table
    # ============================================
    op.create_table(
        'workspace_objects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', sa.String(255), nullable=False),
        sa.Column('type', sa.String(100), nullable=False),
        sa.Column('data', postgresql.JSONB(), nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String()), server_default='{}'),
        sa.Column('created_by_type', sa.String(50), nullable=True),
        sa.Column('created_by_id', sa.String(255), nullable=True),
        sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Basic indexes
    op.create_index('idx_workspace_org', 'workspace_objects', ['org_id'])
    op.create_index('idx_workspace_type', 'workspace_objects', ['type'])
    op.create_index('idx_workspace_org_type', 'workspace_objects', ['org_id', 'type'])
    op.create_index('idx_workspace_created', 'workspace_objects', ['created_at'])
    op.create_index('idx_workspace_created_by', 'workspace_objects', ['created_by_type', 'created_by_id'])

    # GIN indexes for JSONB and array columns
    op.create_index('idx_workspace_tags', 'workspace_objects', ['tags'], postgresql_using='gin')
    # JSONB GIN index with jsonb_ops operator class for full JSON querying
    op.execute('CREATE INDEX idx_workspace_data ON workspace_objects USING gin (data jsonb_ops)')
    op.create_index('idx_workspace_search', 'workspace_objects', ['search_vector'], postgresql_using='gin')

    # ============================================
    # 2. Full-text search trigger
    # ============================================
    # Creates/updates search_vector from common text fields in data
    op.execute('''
        CREATE OR REPLACE FUNCTION workspace_objects_search_trigger()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english',
                coalesce(NEW.data->>'title', '') || ' ' ||
                coalesce(NEW.data->>'name', '') || ' ' ||
                coalesce(NEW.data->>'description', '') || ' ' ||
                coalesce(NEW.data->>'summary', '') || ' ' ||
                coalesce(NEW.data->>'email', '') || ' ' ||
                coalesce(NEW.data->>'content', '') || ' ' ||
                coalesce(NEW.data->>'notes', '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    ''')

    op.execute('''
        CREATE TRIGGER workspace_objects_search_update
            BEFORE INSERT OR UPDATE ON workspace_objects
            FOR EACH ROW EXECUTE FUNCTION workspace_objects_search_trigger();
    ''')

    # ============================================
    # 3. workspace_type_schemas table
    # ============================================
    op.create_table(
        'workspace_type_schemas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', sa.String(255), nullable=False),
        sa.Column('type_name', sa.String(100), nullable=False),
        sa.Column('schema', postgresql.JSONB(), nullable=False),
        sa.Column('is_strict', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Indexes
    op.create_index('idx_type_schema_org', 'workspace_type_schemas', ['org_id'])
    op.create_index('idx_type_schema_type', 'workspace_type_schemas', ['type_name'])

    # Unique constraint on org_id + type_name
    op.create_unique_constraint('uq_workspace_type_schema', 'workspace_type_schemas', ['org_id', 'type_name'])


def downgrade() -> None:
    # Drop workspace_type_schemas
    op.drop_constraint('uq_workspace_type_schema', 'workspace_type_schemas', type_='unique')
    op.drop_index('idx_type_schema_type', table_name='workspace_type_schemas')
    op.drop_index('idx_type_schema_org', table_name='workspace_type_schemas')
    op.drop_table('workspace_type_schemas')

    # Drop trigger and function
    op.execute('DROP TRIGGER IF EXISTS workspace_objects_search_update ON workspace_objects')
    op.execute('DROP FUNCTION IF EXISTS workspace_objects_search_trigger()')

    # Drop workspace_objects indexes
    op.drop_index('idx_workspace_search', table_name='workspace_objects')
    op.drop_index('idx_workspace_data', table_name='workspace_objects')
    op.drop_index('idx_workspace_tags', table_name='workspace_objects')
    op.drop_index('idx_workspace_created_by', table_name='workspace_objects')
    op.drop_index('idx_workspace_created', table_name='workspace_objects')
    op.drop_index('idx_workspace_org_type', table_name='workspace_objects')
    op.drop_index('idx_workspace_type', table_name='workspace_objects')
    op.drop_index('idx_workspace_org', table_name='workspace_objects')

    # Drop workspace_objects table
    op.drop_table('workspace_objects')
