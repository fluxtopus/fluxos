# REVIEW: Several JSON/ARRAY columns use mutable defaults (`default={}`/`[]`),
# REVIEW: which can lead to shared state across instances. Prefer `default=dict`
# REVIEW: or `default=list`. Also note many fields are free-form strings without
# REVIEW: enums/constraints, which can drift.
"""
SQLAlchemy models for the Unified Capability System.

This module defines the database tables for:
- AgentCapability: LLM-powered agents with system prompts and I/O schemas
- Primitive: Simple composable operations (no LLM)
- Plugin: Service bundles (builtin, config-based HTTP, MCP servers)
- PluginOperation: Operations for config-based plugins
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, Boolean, ForeignKey, Index, UniqueConstraint, Integer
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from src.interfaces.database import Base


class AgentCapability(Base):
    """
    LLM-powered agent capability.

    Agents are capabilities that use LLMs to process inputs and generate outputs.
    They are defined by a system prompt and input/output schemas.

    This replaces the fragmented domain subagent classes with a single
    database-driven configuration model.
    """
    __tablename__ = "capabilities_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Identity
    agent_type = Column(String(100), nullable=False)  # e.g., "summarize", "web_research"
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    domain = Column(String(100), nullable=True)  # content, research, analytics, etc.

    # LLM Configuration
    task_type = Column(String(50), nullable=False, default="general")  # general, reasoning, creative
    system_prompt = Column(Text, nullable=False)

    # Schemas (JSON Schema format)
    inputs_schema = Column(JSONB, nullable=False, default={})
    outputs_schema = Column(JSONB, nullable=False, default={})

    # Documentation
    examples = Column(JSONB, nullable=True, default=[])

    # Execution hints for the planner
    # e.g., {"deterministic": false, "speed": "slow", "cost": "high"}
    execution_hints = Column(JSONB, nullable=True, default={})

    # Flags
    is_system = Column(Boolean, nullable=False, default=False)  # True = shipped with platform
    is_active = Column(Boolean, nullable=False, default=True)

    # Ownership
    created_by = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Versioning (CAP-001)
    version = Column(Integer, nullable=False, default=1)
    is_latest = Column(Boolean, nullable=False, default=True)

    # Categorization
    tags = Column(ARRAY(String(100)), nullable=True, default=[])
    keywords = Column(ARRAY(String(100)), nullable=True, default=[])

    # Original specification (CAP-006)
    spec_yaml = Column(Text, nullable=True)

    # Semantic search (CAP-003)
    description_embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small
    embedding_status = Column(String(20), nullable=True, default="pending")

    # Analytics (CAP-002)
    usage_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('organization_id', 'agent_type', 'version', name='uq_cap_agents_org_type_version'),
        Index('idx_cap_agents_org', 'organization_id'),
        Index('idx_cap_agents_type', 'agent_type'),
        Index('idx_cap_agents_domain', 'domain'),
        Index('idx_cap_agents_system', 'is_system'),
        Index('idx_cap_agents_active', 'is_active'),
        Index('idx_cap_agents_latest', 'is_latest'),
        Index('idx_cap_agents_tags', 'tags', postgresql_using='gin'),
    )


class Primitive(Base):
    """
    Simple composable operation (no LLM).

    Primitives are deterministic tools that perform specific operations
    without LLM involvement. They are fast, predictable, and composable.

    Categories: http, json, list, string, control, state, human
    """
    __tablename__ = "capabilities_primitives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    name = Column(String(100), nullable=False, unique=True)  # e.g., "http.get", "json.parse"
    category = Column(String(50), nullable=False)  # http, json, list, string, control, state, human
    description = Column(Text, nullable=True)

    # Schemas (JSON Schema format)
    inputs_schema = Column(JSONB, nullable=False, default={})
    outputs_schema = Column(JSONB, nullable=False, default={})

    # Implementation
    handler_ref = Column(String(255), nullable=False)  # Python path to handler function

    # Execution hints for the planner
    # e.g., {"deterministic": true, "speed": "fast", "cost": "free"}
    execution_hints = Column(JSONB, nullable=True, default={})

    # Flags
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_cap_primitives_name', 'name'),
        Index('idx_cap_primitives_category', 'category'),
        Index('idx_cap_primitives_active', 'is_active'),
    )


class Plugin(Base):
    """
    Service bundle (builtin, config-based HTTP, or MCP server).

    Plugins represent external services that can be called by agents.
    They can be:
    - builtin: Platform services like Den (file storage) or Mimic (notifications)
    - config: User-defined HTTP integrations via configuration
    - mcp: MCP server connections for custom tools
    """
    __tablename__ = "capabilities_plugins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Identity
    namespace = Column(String(100), nullable=False)  # e.g., "den", "mimic", "my_crm"
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Type and Configuration
    plugin_type = Column(String(50), nullable=False)  # builtin, config, mcp
    config = Column(JSONB, nullable=False, default={})  # HTTP config or MCP server URL
    auth_config = Column(JSONB, nullable=True)  # Auth type, secret refs

    # Flags
    is_system = Column(Boolean, nullable=False, default=False)  # True = shipped with platform
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    operations = relationship("PluginOperation", back_populates="plugin", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('organization_id', 'namespace', name='uq_cap_plugins_org_namespace'),
        Index('idx_cap_plugins_org', 'organization_id'),
        Index('idx_cap_plugins_namespace', 'namespace'),
        Index('idx_cap_plugins_type', 'plugin_type'),
        Index('idx_cap_plugins_system', 'is_system'),
        Index('idx_cap_plugins_active', 'is_active'),
    )


class PluginOperation(Base):
    """
    Operation for config-based plugins.

    Each operation defines a specific action that can be performed
    via the plugin, with URL templates, body templates, and I/O schemas.
    """
    __tablename__ = "capabilities_plugin_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_id = Column(UUID(as_uuid=True), ForeignKey("capabilities_plugins.id", ondelete="CASCADE"), nullable=False)

    # Identity
    operation_name = Column(String(100), nullable=False)  # e.g., "upload", "send_email"
    description = Column(Text, nullable=True)

    # HTTP Configuration (for config-type plugins)
    method = Column(String(10), nullable=True)  # GET, POST, PUT, DELETE, etc.
    url_template = Column(Text, nullable=True)  # URL with {variable} placeholders
    body_template = Column(JSONB, nullable=True)
    headers_template = Column(JSONB, nullable=True)

    # Schemas (JSON Schema format)
    inputs_schema = Column(JSONB, nullable=False, default={})
    outputs_mapping = Column(JSONB, nullable=True)  # How to extract response

    # Flags
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    plugin = relationship("Plugin", back_populates="operations")

    __table_args__ = (
        UniqueConstraint('plugin_id', 'operation_name', name='uq_cap_plugin_ops_plugin_name'),
        Index('idx_cap_plugin_ops_plugin', 'plugin_id'),
        Index('idx_cap_plugin_ops_name', 'operation_name'),
    )
