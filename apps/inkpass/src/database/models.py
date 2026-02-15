"""SQLAlchemy models"""

from sqlalchemy import Column, String, Boolean, Text, ForeignKey, TIMESTAMP, Numeric, JSON, Table, BigInteger
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from src.database.database import Base
import uuid

# Association tables for many-to-many relationships
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id"), primary_key=True),
    Column("group_id", String, ForeignKey("groups.id"), primary_key=True)
)

group_permissions = Table(
    "group_permissions",
    Base.metadata,
    Column("group_id", String, ForeignKey("groups.id"), primary_key=True),
    Column("permission_id", String, ForeignKey("permissions.id"), primary_key=True)
)

user_permissions = Table(
    "user_permissions",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id"), primary_key=True),
    Column("permission_id", String, ForeignKey("permissions.id"), primary_key=True)
)

product_plan_permissions = Table(
    "product_plan_permissions",
    Base.metadata,
    Column("product_plan_id", String, ForeignKey("product_plans.id"), primary_key=True),
    Column("permission_id", String, ForeignKey("permissions.id"), primary_key=True),
    Column("created_at", TIMESTAMP, server_default=func.now())
)

# Association table for role template permissions
role_template_permissions = Table(
    "role_template_permissions",
    Base.metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("role_template_id", String, ForeignKey("role_templates.id"), nullable=False),
    Column("resource", String, nullable=False),
    Column("action", String, nullable=False),
)


def generate_id():
    """Generate a unique ID"""
    return str(uuid.uuid4())


class Organization(Base):
    """Organization model"""
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    settings = Column(JSONB, default={})
    plan_id = Column(String)
    storage_quota_bytes = Column(BigInteger, default=5368709120)  # 5GB default
    storage_used_bytes = Column(BigInteger, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Billing fields
    stripe_customer_id = Column(String(255), nullable=True)
    subscription_status = Column(String(50), default="none")  # none, active, past_due, canceled
    subscription_tier = Column(String(50), default="free")    # free, pro, enterprise
    subscription_id = Column(String(255), nullable=True)
    subscription_ends_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    groups = relationship("Group", back_populates="organization", cascade="all, delete-orphan")
    permissions = relationship("Permission", back_populates="organization", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="organization", cascade="all, delete-orphan")
    product_plans = relationship("ProductPlan", back_populates="organization", cascade="all, delete-orphan")
    files = relationship("File", back_populates="organization", cascade="all, delete-orphan")
    billing_config = relationship("BillingConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    email = Column(String, unique=True, nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    password_hash = Column(String, nullable=True)  # Nullable for OAuth-only users
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    product_plan_id = Column(String, ForeignKey("product_plans.id"))  # User's subscription tier
    status = Column(String, default="active")
    two_fa_enabled = Column(Boolean, default=False)
    two_fa_secret = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="users")
    product_plan = relationship("ProductPlan", back_populates="users")
    groups = relationship("Group", secondary="user_groups", back_populates="users")
    user_permissions = relationship("Permission", secondary="user_permissions", back_populates="users")
    api_keys = relationship("APIKey", back_populates="user")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    otp_codes = relationship("OTPCode", back_populates="user", cascade="all, delete-orphan")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    organizations = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")


class Group(Base):
    """Group model"""
    __tablename__ = "groups"
    
    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="groups")
    users = relationship("User", secondary="user_groups", back_populates="groups")
    permissions = relationship("Permission", secondary="group_permissions", back_populates="groups")


class Permission(Base):
    """Permission model"""
    __tablename__ = "permissions"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    resource = Column(String, nullable=False)
    action = Column(String, nullable=False)
    conditions = Column(JSONB, default={})
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="permissions")
    groups = relationship("Group", secondary="group_permissions", back_populates="permissions")
    users = relationship("User", secondary="user_permissions", back_populates="user_permissions")
    product_plans = relationship("ProductPlan", secondary="product_plan_permissions", back_populates="permissions")


class APIKey(Base):
    """API Key model"""
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"))
    key_hash = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    scopes = Column(JSONB, default=[])
    expires_at = Column(TIMESTAMP)
    last_used_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")


class Session(Base):
    """Session model"""
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="sessions")


class OTPCode(Base):
    """OTP Code model"""
    __tablename__ = "otp_codes"
    
    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    code_hash = Column(String, nullable=False)
    purpose = Column(String, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    used_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="otp_codes")


class ProductPlan(Base):
    """
    Product Plan model for subscription-based permissions.

    Defines tiers (Basic, Advanced, Premium, etc.) with associated permissions.
    When a user is assigned a product plan, they automatically receive all
    permissions defined for that plan.

    Examples:
        - Free: Read-only access
        - Basic: Read/write workflows, limited agents
        - Premium: Full access to all resources
    """
    __tablename__ = "product_plans"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    # Plan details
    features = Column(JSONB, default={})  # Feature flags
    limits = Column(JSONB, default={})     # Usage limits (API calls, storage, etc.)
    price = Column(Numeric(10, 2))         # Monthly price
    plan_metadata = Column(JSONB, default={})   # Additional metadata

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="product_plans")
    permissions = relationship(
        "Permission",
        secondary="product_plan_permissions",
        back_populates="product_plans"
    )
    users = relationship("User", back_populates="product_plan")

    def to_dict(self):
        """Convert product plan to dictionary."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "is_active": self.is_active,
            "features": self.features or {},
            "limits": self.limits or {},
            "price": float(self.price) if self.price else None,
            "metadata": self.plan_metadata or {},
            "permission_count": len(self.permissions) if self.permissions else 0,
            "user_count": len(self.users) if self.users else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_with_permissions(self):
        """Convert product plan to dictionary with full permission details."""
        data = self.to_dict()
        data["permissions"] = [
            {
                "id": p.id,
                "resource": p.resource,
                "action": p.action,
                "conditions": p.conditions or {}
            }
            for p in (self.permissions or [])
        ]
        return data


class OAuthProvider(Base):
    """OAuth Provider model for social login"""
    __tablename__ = "oauth_providers"

    id = Column(String, primary_key=True, default=generate_id)
    provider_name = Column(String(50), unique=True, nullable=False)  # e.g., "google", "apple"
    client_id = Column(String(255), nullable=False)
    client_secret = Column(String(255), nullable=False)  # Should be encrypted
    authorization_url = Column(String(500), nullable=False)
    token_url = Column(String(500), nullable=False)
    user_info_url = Column(String(500), nullable=False)
    scopes = Column(JSON, default=list)  # List of OAuth scopes
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    oauth_accounts = relationship("OAuthAccount", back_populates="provider", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert provider to dictionary (excluding secrets)"""
        return {
            "id": self.id,
            "provider_name": self.provider_name,
            "authorization_url": self.authorization_url,
            "is_active": self.is_active,
            "scopes": self.scopes or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OAuthAccount(Base):
    """OAuth Account model linking users to OAuth providers"""
    __tablename__ = "oauth_accounts"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider_id = Column(String, ForeignKey("oauth_providers.id"), nullable=False)
    provider_user_id = Column(String(255), nullable=False)  # User's ID from OAuth provider
    access_token = Column(Text, nullable=True)  # Should be encrypted
    refresh_token = Column(Text, nullable=True)  # Should be encrypted
    token_expires_at = Column(TIMESTAMP, nullable=True)
    profile_data = Column(JSON, default=dict)  # Store name, email, avatar, etc.
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="oauth_accounts")
    provider = relationship("OAuthProvider", back_populates="oauth_accounts")

    def to_dict(self):
        """Convert OAuth account to dictionary (excluding tokens)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider_id": self.provider_id,
            "provider_name": self.provider.provider_name if self.provider else None,
            "provider_user_id": self.provider_user_id,
            "profile_data": self.profile_data or {},
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserOrganization(Base):
    """User-Organization many-to-many relationship for multi-org support"""
    __tablename__ = "user_organizations"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    role = Column(String(50), default="member", nullable=False)
    role_template_id = Column(String, ForeignKey("role_templates.id"), nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    joined_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization")
    role_template = relationship("RoleTemplate", back_populates="user_organizations")

    def to_dict(self):
        """Convert user-organization to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "organization_name": self.organization.name if self.organization else None,
            "role": self.role,
            "role_template_id": self.role_template_id,
            "role_template_name": self.role_template.role_name if self.role_template else None,
            "is_primary": self.is_primary,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }


class OrganizationPlan(Base):
    """Organization Plan subscription model"""
    __tablename__ = "organization_plans"

    organization_id = Column(String, ForeignKey("organizations.id"), primary_key=True)
    plan_id = Column(String, ForeignKey("product_plans.id"), primary_key=True)
    starts_at = Column(TIMESTAMP, primary_key=True)
    ends_at = Column(TIMESTAMP)
    status = Column(String, default="active")


class File(Base):
    """File model for Den file storage"""
    __tablename__ = "files"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    storage_key = Column(String(512), unique=True, nullable=False)
    content_type = Column(String(127), nullable=False)
    size_bytes = Column(sa.BigInteger, nullable=False)
    checksum_sha256 = Column(String(64), nullable=True)
    folder_path = Column(String(1024), default="/")
    tags = Column(JSONB, default=[])
    custom_metadata = Column(JSONB, default={})
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_by_agent = Column(String(127), nullable=True)
    workflow_id = Column(String(127), nullable=True)
    status = Column(String(31), default="active")
    is_temporary = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(TIMESTAMP, nullable=True)
    expires_at = Column(TIMESTAMP, nullable=True)

    # Semantic search columns
    embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small
    embedding_status = Column(String(31), default="pending")  # pending, processing, completed, failed

    # Relationships
    organization = relationship("Organization", back_populates="files")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    access_logs = relationship("FileAccessLog", back_populates="file", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert file to dictionary"""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "storage_key": self.storage_key,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "folder_path": self.folder_path,
            "tags": self.tags or [],
            "custom_metadata": self.custom_metadata or {},
            "created_by_user_id": self.created_by_user_id,
            "created_by_agent": self.created_by_agent,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "is_temporary": self.is_temporary,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "embedding_status": self.embedding_status,
        }

    def is_expired(self):
        """Check if file has expired"""
        from datetime import datetime
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def is_active(self):
        """Check if file is active (not deleted and not expired)"""
        return self.status == "active" and not self.is_expired()


class FileAccessLog(Base):
    """File access audit log"""
    __tablename__ = "file_access_logs"

    id = Column(String, primary_key=True, default=generate_id)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    organization_id = Column(String, nullable=False)
    action = Column(String(31), nullable=False)  # create, read, update, delete, download
    accessor_type = Column(String(31), nullable=False)  # user, agent, service
    accessor_id = Column(String(127), nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    file = relationship("File", back_populates="access_logs")

    def to_dict(self):
        """Convert access log to dictionary"""
        return {
            "id": self.id,
            "file_id": self.file_id,
            "organization_id": self.organization_id,
            "action": self.action,
            "accessor_type": self.accessor_type,
            "accessor_id": self.accessor_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BillingConfig(Base):
    """
    Billing configuration for an organization.

    Stores encrypted Stripe credentials and price mappings.
    Each organization can have its own Stripe configuration
    (e.g., a control-plane service passes its Stripe keys to InkPass for its org).
    """
    __tablename__ = "billing_configs"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), unique=True, nullable=False)
    stripe_api_key_encrypted = Column(Text, nullable=False)
    stripe_webhook_secret_encrypted = Column(Text, nullable=True)
    price_ids = Column(JSONB, default={})  # {"pro": "price_xxx", "enterprise": "price_yyy"}
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="billing_config")

    def to_dict(self):
        """Convert billing config to dictionary (excluding secrets)"""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "price_ids": self.price_ids or {},
            "has_api_key": bool(self.stripe_api_key_encrypted),
            "has_webhook_secret": bool(self.stripe_webhook_secret_encrypted),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# PERMISSION TEMPLATE SYSTEM
# =============================================================================


class PermissionTemplate(Base):
    """
    Global permission template registry (not org-scoped).

    Templates define permission sets for different product types
    (TENTACKL_SOLO, MIMIC_SOLO, INKPASS_SOLO, AIOS_BUNDLE).
    Templates are defined in code and synced to DB via admin API.
    """
    __tablename__ = "permission_templates"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, unique=True, nullable=False)  # e.g., "TENTACKL_SOLO"
    product_type = Column(String, nullable=False)  # Maps to ProductType enum
    version = Column(sa.Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    roles = relationship("RoleTemplate", back_populates="template", cascade="all, delete-orphan")
    organization_templates = relationship("OrganizationTemplate", back_populates="template")

    def to_dict(self):
        """Convert template to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "product_type": self.product_type,
            "version": self.version,
            "description": self.description,
            "is_active": self.is_active,
            "role_count": len(self.roles) if self.roles else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_with_roles(self):
        """Convert template to dictionary with role details"""
        data = self.to_dict()
        data["roles"] = [role.to_dict() for role in (self.roles or [])]
        return data


class RoleTemplate(Base):
    """
    Role within a permission template (owner, admin, developer, viewer).

    Defines a named role with associated permissions. Roles can inherit
    from other roles (e.g., developer inherits from viewer).
    """
    __tablename__ = "role_templates"

    id = Column(String, primary_key=True, default=generate_id)
    template_id = Column(String, ForeignKey("permission_templates.id"), nullable=False)
    role_name = Column(String, nullable=False)  # "owner", "admin", "developer", "viewer"
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    inherits_from = Column(String, nullable=True)  # Role name to inherit from
    priority = Column(sa.Integer, default=0)  # Higher = more permissions

    # Relationships
    template = relationship("PermissionTemplate", back_populates="roles")
    user_organizations = relationship("UserOrganization", back_populates="role_template")

    # Unique constraint per template
    __table_args__ = (
        sa.UniqueConstraint("template_id", "role_name", name="uq_role_template_name"),
    )

    def to_dict(self):
        """Convert role template to dictionary"""
        return {
            "id": self.id,
            "template_id": self.template_id,
            "role_name": self.role_name,
            "display_name": self.display_name,
            "description": self.description,
            "inherits_from": self.inherits_from,
            "priority": self.priority,
        }

    def to_dict_with_permissions(self):
        """Convert role template to dictionary with permissions"""
        from sqlalchemy.orm import Session
        from sqlalchemy import select
        data = self.to_dict()
        # Get permissions from association table
        session = Session.object_session(self)
        if session:
            result = session.execute(
                select(role_template_permissions.c.resource, role_template_permissions.c.action)
                .where(role_template_permissions.c.role_template_id == self.id)
            )
            data["permissions"] = [
                {"resource": row.resource, "action": row.action}
                for row in result.fetchall()
            ]
        else:
            data["permissions"] = []
        return data


class OrganizationTemplate(Base):
    """
    Tracks which template(s) an organization uses.

    When a template is applied to an org, this records the version
    that was applied. Used to determine if an org needs to be
    updated when a template version increases.
    """
    __tablename__ = "organization_templates"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    template_id = Column(String, ForeignKey("permission_templates.id"), nullable=False)
    applied_version = Column(sa.Integer, nullable=False)
    applied_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    organization = relationship("Organization")
    template = relationship("PermissionTemplate", back_populates="organization_templates")

    # Unique constraint: one template per org
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "template_id", name="uq_org_template"),
    )

    def to_dict(self):
        """Convert org template to dictionary"""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "template_id": self.template_id,
            "template_name": self.template.name if self.template else None,
            "applied_version": self.applied_version,
            "current_version": self.template.version if self.template else None,
            "needs_update": (
                self.template.version > self.applied_version
                if self.template else False
            ),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


class OrganizationCustomPermission(Base):
    """
    Tracks the source of each permission in an organization.

    Permissions can come from a template ('template') or be added
    manually ('custom'). This allows orgs to add custom permissions
    on top of their template permissions.
    """
    __tablename__ = "organization_custom_permissions"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    permission_id = Column(String, ForeignKey("permissions.id"), nullable=False)
    source = Column(String, default="custom", nullable=False)  # 'template' or 'custom'
    granted_by = Column(String, nullable=True)  # User ID who granted it
    granted_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    organization = relationship("Organization")
    permission = relationship("Permission")

    # Unique constraint: one entry per org/permission pair
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "permission_id", name="uq_org_custom_permission"),
    )


class Invitation(Base):
    """
    User invitation model for email-based user onboarding.

    Enables admins to invite users to their organization via email.
    Invited users receive a secure token link to accept and create
    their account with a specified role.

    Flow:
        1. Admin creates invitation (email + role)
        2. System emails invite link with token
        3. User clicks link, sets password
        4. User account created with invited role
    """
    __tablename__ = "invitations"

    id = Column(String, primary_key=True, default=generate_id)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String(50), default="member", nullable=False)  # viewer, member, developer, admin
    token_hash = Column(String, unique=True, nullable=False)  # SHA-256 hash of token
    invited_by_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, accepted, expired, revoked
    expires_at = Column(TIMESTAMP, nullable=False)
    accepted_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    organization = relationship("Organization")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])

    # Indexes for common queries
    __table_args__ = (
        sa.Index("ix_invitations_organization_id", "organization_id"),
        sa.Index("ix_invitations_email", "email"),
        sa.Index("ix_invitations_token_hash", "token_hash"),
        sa.Index("ix_invitations_status", "status"),
    )

    def to_dict(self):
        """Convert invitation to dictionary"""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "invited_by_user_id": self.invited_by_user_id,
            "invited_by_email": self.invited_by.email if self.invited_by else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_valid(self):
        """Check if invitation is valid (pending and not expired)"""
        from datetime import datetime
        if self.status != "pending":
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
