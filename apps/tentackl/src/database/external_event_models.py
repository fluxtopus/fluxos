"""SQLAlchemy models for external event publishing."""

from datetime import datetime
import uuid

from sqlalchemy import Column, String, DateTime, Integer, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from src.interfaces.database import Base


class ExternalPublisher(Base):
    """External API publishers with authentication."""
    __tablename__ = "external_publishers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    api_key_hash = Column(String(255), nullable=False, unique=True)
    permissions = Column(ARRAY(String), nullable=False, default=[])
    rate_limit = Column(Integer, nullable=True)  # requests per minute
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_publisher_api_key", "api_key_hash"),
        Index("idx_publisher_active", "is_active"),
    )
