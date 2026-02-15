"""Add Agent Memory System columns

Revision ID: 20260110_memory
Revises: 20260109_embedding
Create Date: 2026-01-10

This migration adds columns for the Agent Memory System:

1. UserPreference extensions:
   - scope, scope_value: Preference scoping (global, agent_type, task_type, task)
   - preference_type: "auto_approval" or "instruction"
   - instruction: Human-readable instruction for prompt injection
   - source: How the preference was created

2. CheckpointApproval extensions:
   - checkpoint_type: Interactive checkpoint types (approval, input, modify, select, qa)
   - input_schema, questions, alternatives: Checkpoint configuration
   - response_*: User response data from interactive checkpoints

3. AgentSpec extensions:
   - description_embedding: Vector for semantic agent discovery
   - brief, keywords, capabilities: Enhanced metadata for discovery
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260110_memory'
down_revision: Union[str, None] = '20260109_embedding'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================
    # 1. UserPreference - Rich Preferences
    # ============================================

    # Scope for preference application
    op.add_column('user_preferences', sa.Column(
        'scope',
        sa.String(50),
        server_default='global',
        nullable=False
    ))

    # Value for scope (e.g., "notify" for agent_type scope)
    op.add_column('user_preferences', sa.Column(
        'scope_value',
        sa.String(255),
        nullable=True
    ))

    # Type of preference: auto_approval or instruction
    op.add_column('user_preferences', sa.Column(
        'preference_type',
        sa.String(50),
        server_default='auto_approval',
        nullable=False
    ))

    # Human-readable instruction for prompt injection
    op.add_column('user_preferences', sa.Column(
        'instruction',
        sa.Text(),
        nullable=True
    ))

    # Source tracking: learned, manual, imported
    op.add_column('user_preferences', sa.Column(
        'source',
        sa.String(50),
        server_default='learned',
        nullable=False
    ))

    # Indexes for scoped preference lookups
    op.create_index('idx_pref_scope', 'user_preferences', ['scope'])
    op.create_index('idx_pref_user_scope', 'user_preferences', ['user_id', 'scope'])
    op.create_index('idx_pref_user_scope_value', 'user_preferences', ['user_id', 'scope', 'scope_value'])
    op.create_index('idx_pref_type', 'user_preferences', ['preference_type'])

    # ============================================
    # 2. CheckpointApproval - Interactive Checkpoints
    # ============================================

    # Checkpoint type: approval, input, modify, select, qa
    op.add_column('checkpoint_approvals', sa.Column(
        'checkpoint_type',
        sa.String(50),
        server_default='approval',
        nullable=False
    ))

    # Configuration for interactive checkpoints
    op.add_column('checkpoint_approvals', sa.Column(
        'input_schema',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'questions',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'alternatives',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'modifiable_fields',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'context_data',
        sa.JSON(),
        nullable=True
    ))

    # Response data from interactive checkpoints
    op.add_column('checkpoint_approvals', sa.Column(
        'response_inputs',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'response_modified_inputs',
        sa.JSON(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'response_selected_alternative',
        sa.Integer(),
        nullable=True
    ))

    op.add_column('checkpoint_approvals', sa.Column(
        'response_answers',
        sa.JSON(),
        nullable=True
    ))

    # Index for checkpoint type filtering
    op.create_index('idx_checkpoint_type', 'checkpoint_approvals', ['checkpoint_type'])

    # ============================================
    # 3. AgentSpec - Dynamic Agent Discovery
    # ============================================

    # Embedding for semantic search (pgvector already enabled)
    op.execute('ALTER TABLE agent_specs ADD COLUMN description_embedding vector(1536)')

    # Embedding generation status
    op.add_column('agent_specs', sa.Column(
        'embedding_status',
        sa.String(50),
        server_default='pending',
        nullable=True
    ))

    # Brief one-line description for listings
    op.add_column('agent_specs', sa.Column(
        'brief',
        sa.String(500),
        nullable=True
    ))

    # Keywords for search (separate from tags)
    op.execute("ALTER TABLE agent_specs ADD COLUMN keywords VARCHAR(255)[]")

    # Capabilities this agent uses
    op.execute("ALTER TABLE agent_specs ADD COLUMN capabilities VARCHAR(100)[]")

    # HNSW index for fast vector similarity search on agent specs
    op.execute('''
        CREATE INDEX idx_agent_specs_embedding_hnsw
        ON agent_specs USING hnsw (description_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE description_embedding IS NOT NULL
    ''')

    # Index for embedding status
    op.create_index('idx_agent_specs_embedding_status', 'agent_specs', ['embedding_status'])

    # Index for capability-based filtering
    op.create_index('idx_agent_specs_capabilities', 'agent_specs', ['capabilities'], postgresql_using='gin')


def downgrade() -> None:
    # AgentSpec
    op.execute('DROP INDEX IF EXISTS idx_agent_specs_capabilities')
    op.execute('DROP INDEX IF EXISTS idx_agent_specs_embedding_status')
    op.execute('DROP INDEX IF EXISTS idx_agent_specs_embedding_hnsw')
    op.execute('ALTER TABLE agent_specs DROP COLUMN IF EXISTS capabilities')
    op.execute('ALTER TABLE agent_specs DROP COLUMN IF EXISTS keywords')
    op.drop_column('agent_specs', 'brief')
    op.drop_column('agent_specs', 'embedding_status')
    op.execute('ALTER TABLE agent_specs DROP COLUMN IF EXISTS description_embedding')

    # CheckpointApproval
    op.drop_index('idx_checkpoint_type', table_name='checkpoint_approvals')
    op.drop_column('checkpoint_approvals', 'response_answers')
    op.drop_column('checkpoint_approvals', 'response_selected_alternative')
    op.drop_column('checkpoint_approvals', 'response_modified_inputs')
    op.drop_column('checkpoint_approvals', 'response_inputs')
    op.drop_column('checkpoint_approvals', 'context_data')
    op.drop_column('checkpoint_approvals', 'modifiable_fields')
    op.drop_column('checkpoint_approvals', 'alternatives')
    op.drop_column('checkpoint_approvals', 'questions')
    op.drop_column('checkpoint_approvals', 'input_schema')
    op.drop_column('checkpoint_approvals', 'checkpoint_type')

    # UserPreference
    op.drop_index('idx_pref_type', table_name='user_preferences')
    op.drop_index('idx_pref_user_scope_value', table_name='user_preferences')
    op.drop_index('idx_pref_user_scope', table_name='user_preferences')
    op.drop_index('idx_pref_scope', table_name='user_preferences')
    op.drop_column('user_preferences', 'source')
    op.drop_column('user_preferences', 'instruction')
    op.drop_column('user_preferences', 'preference_type')
    op.drop_column('user_preferences', 'scope_value')
    op.drop_column('user_preferences', 'scope')
