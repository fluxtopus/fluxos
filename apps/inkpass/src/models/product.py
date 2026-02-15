"""Product/Plan models for subscription-based permissions."""

from datetime import datetime
from typing import Optional, List, Any
from uuid import uuid4

from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.database.base import Base


# Association table for product-permission relationship
product_permissions = Table(
    'product_permissions',
    Base.metadata,
    Column('product_id', UUID(as_uuid=True), ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', UUID(as_uuid=True), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow)
)


class Product(Base):
    """
    Product/Plan model for subscription-based permissions.

    Products define tiers (Basic, Advanced, Premium, etc.) with associated
    permissions. When a user is assigned a product, they automatically
    receive all permissions defined for that product.

    Examples:
        - Basic: Read-only access to workflows
        - Advanced: Read/write workflows, limited agents
        - Premium: Full access to all resources
    """
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete='CASCADE'), nullable=False, index=True)

    # Product identity
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, index=True)
    description = Column(String(500))

    # Product state
    is_active = Column(Boolean, default=True, nullable=False)

    # Additional metadata (pricing, features, limits, etc.)
    metadata = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="products")
    permissions = relationship(
        "Permission",
        secondary=product_permissions,
        back_populates="products",
        lazy="selectin"  # Eager load permissions
    )
    users = relationship("User", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, slug={self.slug})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert product to dictionary."""
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "is_active": self.is_active,
            "metadata": self.metadata or {},
            "permission_count": len(self.permissions) if self.permissions else 0,
            "user_count": len(self.users) if self.users else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_with_permissions(self) -> dict[str, Any]:
        """Convert product to dictionary with full permission details."""
        data = self.to_dict()
        data["permissions"] = [
            {
                "id": str(p.id),
                "resource": p.resource,
                "action": p.action,
                "conditions": p.conditions or {}
            }
            for p in (self.permissions or [])
        ]
        return data
