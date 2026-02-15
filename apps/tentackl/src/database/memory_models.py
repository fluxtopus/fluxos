# REVIEW: Multiple columns use mutable defaults (`default=[]`/`{}`), which can
# REVIEW: lead to shared state. Prefer `default=list` / `default=dict`.
"""SQLAlchemy models for the memory service.

This module defines the database tables for:
- Memory: Knowledge artifacts stored by users and agents
- MemoryVersion: Version history for memory content
- MemoryPermission: Access control for individual memories
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Integer, Boolean,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from src.interfaces.database import Base


class Memory(Base):
    """Knowledge artifact stored by users or agents."""
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(String(255), nullable=False, index=True)
    key = Column(String(500), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    scope = Column(String(50), nullable=False, default="organization")
    scope_value = Column(String(255), nullable=True)
    tags = Column(ARRAY(String), nullable=True, default=[])
    topic = Column(String(255), nullable=True, index=True)
    content_type = Column(String(100), nullable=False, default="text")
    current_version = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="active")
    created_by_user_id = Column(String(255), nullable=True, index=True)
    created_by_agent_id = Column(String(255), nullable=True, index=True)
    extra_metadata = Column('metadata', JSON, nullable=True, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Embedding columns for semantic search (added by MEM-025 migration)
    content_embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small
    embedding_status = Column(String(50), nullable=True, default="pending")  # pending, completed, failed

    # Relationships
    versions = relationship("MemoryVersion", back_populates="memory", cascade="all, delete-orphan")
    permissions = relationship("MemoryPermission", back_populates="memory", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_memory_org", "organization_id"),
        UniqueConstraint("organization_id", "key", name="idx_memory_org_key"),
        Index("idx_memory_scope", "scope"),
        Index("idx_memory_org_scope", "organization_id", "scope", "scope_value"),
        Index("idx_memory_topic", "topic"),
        Index("idx_memory_tags", "tags", postgresql_using="gin"),
        Index("idx_memory_created", "created_at"),
    )


class MemoryVersion(Base):
    """Version history for memory content."""
    __tablename__ = "memory_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    body = Column(Text, nullable=False)
    extended_data = Column(JSON, nullable=True, default={})
    change_summary = Column(String(500), nullable=True)
    changed_by = Column(String(255), nullable=True)
    changed_by_agent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    memory = relationship("Memory", back_populates="versions")

    # Constraints
    __table_args__ = (
        UniqueConstraint("memory_id", "version", name="uq_memory_version"),
    )


class MemoryPermission(Base):
    """Access control for individual memories."""
    __tablename__ = "memory_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)
    grantee_user_id = Column(String(255), nullable=True)
    grantee_agent_id = Column(String(255), nullable=True)
    permission_level = Column(String(50), nullable=False, default="read")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    memory = relationship("Memory", back_populates="permissions")

    # Indexes
    __table_args__ = (
        Index("idx_memperm_memory", "memory_id"),
        Index("idx_memperm_user", "grantee_user_id"),
        Index("idx_memperm_agent", "grantee_agent_id"),
    )
