"""add_unified_capabilities

Revision ID: 20260118_capabilities
Revises: 20260112_workspace
Create Date: 2026-01-18

This migration adds the Unified Capability System tables:
- capabilities_agents: LLM-powered agents with system prompts and I/O schemas
- capabilities_primitives: Simple composable operations (no LLM)
- capabilities_plugins: Service bundles (builtin, config-based HTTP, MCP servers)
- capabilities_plugin_operations: Operations for config-based plugins
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260118_capabilities"
down_revision = "20260112_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === 1. capabilities_agents ===
    op.create_table(
        "capabilities_agents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("agent_type", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=100), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False, server_default="general"),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("inputs_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("outputs_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="[]"),
        sa.Column("execution_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="{}"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "agent_type", name="uq_cap_agents_org_type"),
    )
    op.create_index("idx_cap_agents_active", "capabilities_agents", ["is_active"], unique=False)
    op.create_index("idx_cap_agents_domain", "capabilities_agents", ["domain"], unique=False)
    op.create_index("idx_cap_agents_org", "capabilities_agents", ["organization_id"], unique=False)
    op.create_index("idx_cap_agents_system", "capabilities_agents", ["is_system"], unique=False)
    op.create_index("idx_cap_agents_type", "capabilities_agents", ["agent_type"], unique=False)

    # === 2. capabilities_primitives ===
    op.create_table(
        "capabilities_primitives",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("inputs_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("outputs_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("handler_ref", sa.String(length=255), nullable=False),
        sa.Column("execution_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_cap_primitives_name"),
    )
    op.create_index("idx_cap_primitives_active", "capabilities_primitives", ["is_active"], unique=False)
    op.create_index("idx_cap_primitives_category", "capabilities_primitives", ["category"], unique=False)
    op.create_index("idx_cap_primitives_name", "capabilities_primitives", ["name"], unique=False)

    # === 3. capabilities_plugins ===
    op.create_table(
        "capabilities_plugins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("plugin_type", sa.String(length=50), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("auth_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "namespace", name="uq_cap_plugins_org_namespace"),
    )
    op.create_index("idx_cap_plugins_active", "capabilities_plugins", ["is_active"], unique=False)
    op.create_index("idx_cap_plugins_namespace", "capabilities_plugins", ["namespace"], unique=False)
    op.create_index("idx_cap_plugins_org", "capabilities_plugins", ["organization_id"], unique=False)
    op.create_index("idx_cap_plugins_system", "capabilities_plugins", ["is_system"], unique=False)
    op.create_index("idx_cap_plugins_type", "capabilities_plugins", ["plugin_type"], unique=False)

    # === 4. capabilities_plugin_operations ===
    op.create_table(
        "capabilities_plugin_operations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plugin_id", sa.UUID(), nullable=False),
        sa.Column("operation_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("url_template", sa.Text(), nullable=True),
        sa.Column("body_template", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("headers_template", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("inputs_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("outputs_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plugin_id"], ["capabilities_plugins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id", "operation_name", name="uq_cap_plugin_ops_plugin_name"),
    )
    op.create_index("idx_cap_plugin_ops_name", "capabilities_plugin_operations", ["operation_name"], unique=False)
    op.create_index("idx_cap_plugin_ops_plugin", "capabilities_plugin_operations", ["plugin_id"], unique=False)


def downgrade() -> None:
    # Drop capabilities_plugin_operations
    op.drop_index("idx_cap_plugin_ops_plugin", table_name="capabilities_plugin_operations")
    op.drop_index("idx_cap_plugin_ops_name", table_name="capabilities_plugin_operations")
    op.drop_table("capabilities_plugin_operations")

    # Drop capabilities_plugins
    op.drop_index("idx_cap_plugins_type", table_name="capabilities_plugins")
    op.drop_index("idx_cap_plugins_system", table_name="capabilities_plugins")
    op.drop_index("idx_cap_plugins_org", table_name="capabilities_plugins")
    op.drop_index("idx_cap_plugins_namespace", table_name="capabilities_plugins")
    op.drop_index("idx_cap_plugins_active", table_name="capabilities_plugins")
    op.drop_table("capabilities_plugins")

    # Drop capabilities_primitives
    op.drop_index("idx_cap_primitives_name", table_name="capabilities_primitives")
    op.drop_index("idx_cap_primitives_category", table_name="capabilities_primitives")
    op.drop_index("idx_cap_primitives_active", table_name="capabilities_primitives")
    op.drop_table("capabilities_primitives")

    # Drop capabilities_agents
    op.drop_index("idx_cap_agents_type", table_name="capabilities_agents")
    op.drop_index("idx_cap_agents_system", table_name="capabilities_agents")
    op.drop_index("idx_cap_agents_org", table_name="capabilities_agents")
    op.drop_index("idx_cap_agents_domain", table_name="capabilities_agents")
    op.drop_index("idx_cap_agents_active", table_name="capabilities_agents")
    op.drop_table("capabilities_agents")
