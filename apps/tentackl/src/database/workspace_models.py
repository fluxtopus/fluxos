# REVIEW: WorkspaceObject uses mutable default for tags and string org_id,
# REVIEW: which can lead to shared state and inconsistent ID typing across models.
"""
SQLAlchemy models for workspace objects system.

This module defines the database tables for:
- WorkspaceObject: Flexible JSONB-based object storage (events, contacts, custom types)
- WorkspaceTypeSchema: Optional JSON Schema definitions for type validation
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, Boolean,
    Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TSVECTOR, JSONB
import uuid

from src.interfaces.database import Base


class WorkspaceObject(Base):
    """
    Flexible object storage for any data type.

    Stores calendar events, contacts, or any custom object type
    using JSONB storage without requiring schema migrations.

    Multi-tenant isolation via org_id.
    Full-text search via auto-maintained search_vector.
    """
    __tablename__ = "workspace_objects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(String(255), nullable=False, index=True)

    # Object type and data
    type = Column(String(100), nullable=False)  # "event", "contact", custom types
    data = Column(JSONB, nullable=False)

    # Extracted for indexing and filtering
    tags = Column(ARRAY(String), default=[])

    # Creator tracking
    created_by_type = Column(String(50), nullable=True)  # "user", "agent"
    created_by_id = Column(String(255), nullable=True)

    # Auto-maintained full-text search vector
    search_vector = Column(TSVECTOR, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_workspace_org", "org_id"),
        Index("idx_workspace_type", "type"),
        Index("idx_workspace_org_type", "org_id", "type"),
        Index("idx_workspace_created", "created_at"),
        Index("idx_workspace_created_by", "created_by_type", "created_by_id"),
        Index("idx_workspace_tags", "tags", postgresql_using="gin"),
        Index("idx_workspace_data", "data", postgresql_using="gin"),
        Index("idx_workspace_search", "search_vector", postgresql_using="gin"),
    )


class WorkspaceTypeSchema(Base):
    """
    Optional schema definitions for type validation.

    Allows registering JSON Schemas for object types to:
    - Validate data on create/update (strict mode rejects, non-strict warns)
    - Document expected structure
    - Enable better tooling and suggestions
    """
    __tablename__ = "workspace_type_schemas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(String(255), nullable=False, index=True)

    # Type definition
    type_name = Column(String(100), nullable=False)
    schema = Column(JSONB, nullable=False)  # JSON Schema
    is_strict = Column(Boolean, nullable=False, default=False)  # Reject vs warn on mismatch

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes and constraints
    __table_args__ = (
        Index("idx_type_schema_org", "org_id"),
        Index("idx_type_schema_type", "type_name"),
        UniqueConstraint("org_id", "type_name", name="uq_workspace_type_schema"),
    )
