# REVIEW: AllowedHost lacks a uniqueness constraint (host+environment), and
# REVIEW: there is no organization scoping, which may be needed for multi-tenant
# REVIEW: deployments.
"""SQLAlchemy models for allowed HTTP hosts management."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, Boolean, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from src.interfaces.database import Base


class Environment(str, enum.Enum):
    """Environment enum for allowed hosts."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    STAGING = "staging"
    TESTING = "testing"


class AllowedHost(Base):
    """Allowed HTTP host model for per-environment allowlist management."""
    __tablename__ = "allowed_hosts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host = Column(String(255), nullable=False)  # Hostname only (e.g., "api.example.com")
    environment = Column(
        SQLEnum(Environment, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Environment.DEVELOPMENT
    )
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)  # User/service that created this entry
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)  # Optional notes about why this host is allowed
    
    # Indexes for efficient lookups
    __table_args__ = (
        Index("idx_allowed_host_host_env", "host", "environment"),
        Index("idx_allowed_host_enabled", "enabled"),
        Index("idx_allowed_host_environment", "environment"),
    )
