# REVIEW: Mutable defaults (`default=[]`, `default={}`) on columns can lead to
# REVIEW: shared state across instances. Prefer `default=list` / `default=dict`.
"""SQLAlchemy models for authentication and API key storage."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Boolean, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid

from src.interfaces.database import Base


class APIKeyModel(Base):
    """API Key model for durable storage in PostgreSQL."""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA256 hash (64 hex chars)
    service_name = Column(String(255), nullable=False)
    scopes = Column(ARRAY(String), nullable=False, default=[])
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)  # Optional audit field
    extra_metadata = Column('metadata', JSON, nullable=True, default={})  # Stores additional metadata
    
    # Indexes
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_key_hash"),
        Index("idx_api_key_hash", "key_hash"),
        Index("idx_api_key_service", "service_name"),
        Index("idx_api_key_active", "is_active"),
        Index("idx_api_key_expires", "expires_at"),
    )
