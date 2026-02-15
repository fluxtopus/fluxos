"""Database models for Mimic Notification Service"""

import enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Numeric, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.database.database import Base
import uuid


# =============================================================================
# Integration System Enums (INT-001 to INT-004)
# =============================================================================


class IntegrationProvider(str, enum.Enum):
    """Supported integration providers."""
    discord = "discord"
    slack = "slack"
    github = "github"
    stripe = "stripe"
    twitter = "twitter"
    custom_webhook = "custom_webhook"


class IntegrationDirection(str, enum.Enum):
    """Direction of integration data flow."""
    inbound = "inbound"
    outbound = "outbound"
    bidirectional = "bidirectional"


class IntegrationStatus(str, enum.Enum):
    """Integration operational status."""
    active = "active"
    paused = "paused"
    error = "error"


class CredentialType(str, enum.Enum):
    """Type of stored credential."""
    api_key = "api_key"
    oauth_token = "oauth_token"
    webhook_url = "webhook_url"
    bot_token = "bot_token"
    webhook_secret = "webhook_secret"


class InboundAuthMethod(str, enum.Enum):
    """Authentication method for inbound webhooks."""
    none = "none"
    api_key = "api_key"
    signature = "signature"    # HMAC-SHA256
    ed25519 = "ed25519"        # Ed25519 (Discord interactions)
    bearer = "bearer"


class DestinationService(str, enum.Enum):
    """Target service for inbound webhook routing."""
    tentackl = "tentackl"
    custom = "custom"


class OutboundActionType(str, enum.Enum):
    """Type of outbound action to perform."""
    send_message = "send_message"
    send_embed = "send_embed"
    send_blocks = "send_blocks"
    create_issue = "create_issue"
    post_comment = "post_comment"
    post = "post"
    put = "put"


class IntegrationWebhookEventStatus(str, enum.Enum):
    """Status of integration webhook event processing."""
    received = "received"
    routing = "routing"
    delivered = "delivered"
    failed = "failed"


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    subscription_tier = Column(String, default="free")  # free, annual
    subscription_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")
    provider_keys = relationship("ProviderKey", back_populates="user", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="user", cascade="all, delete-orphan")
    delivery_logs = relationship("DeliveryLog", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    """API Key model"""
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="api_keys")


class Workflow(Base):
    """Workflow model"""
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    definition_json = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="workflows")
    delivery_logs = relationship("DeliveryLog", back_populates="workflow")


class ProviderKey(Base):
    """Provider Key model (BYOK)"""
    __tablename__ = "provider_keys"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider_type = Column(String, nullable=False)  # email, sms, slack, discord, telegram, webhook
    encrypted_api_key = Column(Text, nullable=True)  # For SendGrid, Twilio, etc.
    encrypted_secret = Column(Text, nullable=True)  # For Twilio account SID, etc.
    webhook_url = Column(String, nullable=True)  # For Slack, Discord, webhook
    bot_token = Column(Text, nullable=True)  # For Telegram (encrypted)
    from_email = Column(String, nullable=True)  # For Email provider
    from_number = Column(String, nullable=True)  # For SMS provider
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="provider_keys")
    
    __table_args__ = (
        {"extend_existing": True},
    )


class Template(Base):
    """Template model"""
    __tablename__ = "templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    variables = Column(JSON, default=list)  # List of variable names
    version = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="templates")


class SystemTemplate(Base):
    """
    Organization-scoped email templates for transactional emails.

    These templates are shared across an organization (or platform-wide if
    organization_id is null). Used for system emails like invitations,
    password resets, welcome emails, etc.

    Template variables use {{variable}} syntax and are substituted at send time.
    """
    __tablename__ = "system_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, nullable=True, index=True)  # null = platform-wide
    name = Column(String(100), nullable=False)  # e.g., "invitation", "welcome"
    subject = Column(String(500), nullable=False)
    content_text = Column(Text, nullable=False)
    content_html = Column(Text, nullable=True)
    variables = Column(JSON, default=list)  # List of variable names
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Unique name per organization (null org = platform template)
        {"extend_existing": True},
    )


class DeliveryLog(Base):
    """Delivery Log model"""
    __tablename__ = "delivery_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    delivery_id = Column(String, unique=True, index=True, nullable=False)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=True)
    provider = Column(String, nullable=False)  # email, sms, slack, etc.
    recipient = Column(String, nullable=False)
    status = Column(String, nullable=False)  # pending, sent, failed, delivered
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    provider_cost = Column(Numeric(10, 4), nullable=True)  # Cost from provider
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="delivery_logs")
    workflow = relationship("Workflow", back_populates="delivery_logs")


# ============================================================================
# Webhook Gateway Models
# ============================================================================


class WebhookEvent(Base):
    """
    Inbound webhook event log.

    Records all webhooks received from external services (Stripe, Resend, etc.)
    for auditing, idempotency, and retry handling.
    """
    __tablename__ = "webhook_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(50), nullable=False, index=True)  # stripe, resend, etc.
    event_type = Column(String(100), nullable=False, index=True)  # checkout.session.completed
    event_id = Column(String(255), nullable=False)  # Provider's event ID
    payload = Column(JSON, nullable=False)  # Raw payload
    signature = Column(String(500), nullable=True)  # For verification audit
    status = Column(String(20), default="received", index=True)  # received, processing, delivered, failed
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    deliveries = relationship("WebhookDelivery", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        # Idempotency: prevent duplicate events from same provider
        {"extend_existing": True},
    )


class WebhookDelivery(Base):
    """
    Webhook delivery tracking to downstream services.

    Tracks each attempt to route a webhook event to internal services
    via Celery queue.
    """
    __tablename__ = "webhook_deliveries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("webhook_events.id"), nullable=False, index=True)
    target_service = Column(String(50), nullable=False)  # inkpass, tentackl, custom, etc.
    task_name = Column(String(255), nullable=False)  # Celery task name
    status = Column(String(20), default="pending")  # pending, success, failed
    celery_task_id = Column(String(255), nullable=True)  # Celery task ID for tracking
    result = Column(JSON, nullable=True)  # Task result or error details
    attempt_count = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    event = relationship("WebhookEvent", back_populates="deliveries")


# =============================================================================
# Integration System Models (INT-001 to INT-004)
# =============================================================================


class Integration(Base):
    """
    Central integration entity (INT-001).

    Represents a connection to an external service (Discord, Slack, GitHub, etc.)
    for a specific organization and user.
    """
    __tablename__ = "integrations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    provider = Column(
        Enum(IntegrationProvider, name="integration_provider_enum", create_type=False),
        nullable=False
    )
    direction = Column(
        Enum(IntegrationDirection, name="integration_direction_enum", create_type=False),
        nullable=False,
        default=IntegrationDirection.bidirectional
    )
    status = Column(
        Enum(IntegrationStatus, name="integration_status_enum", create_type=False),
        nullable=False,
        default=IntegrationStatus.active
    )
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    credentials = relationship("IntegrationCredential", back_populates="integration", cascade="all, delete-orphan")
    inbound_config = relationship("IntegrationInboundConfig", back_populates="integration", uselist=False, cascade="all, delete-orphan")
    outbound_config = relationship("IntegrationOutboundConfig", back_populates="integration", uselist=False, cascade="all, delete-orphan")
    webhook_events = relationship("IntegrationWebhookEvent", back_populates="integration")


class IntegrationCredential(Base):
    """
    Encrypted credential storage for integrations (INT-002).

    Stores API keys, OAuth tokens, webhook URLs, etc. with encryption.
    """
    __tablename__ = "integration_credentials"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(String, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False)
    credential_type = Column(
        Enum(CredentialType, name="credential_type_enum", create_type=False),
        nullable=False
    )
    encrypted_value = Column(Text, nullable=False)
    credential_metadata = Column(JSON, nullable=True)  # Extra fields: from_email, channel_id, etc.
    expires_at = Column(DateTime, nullable=True)  # For OAuth tokens
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    integration = relationship("Integration", back_populates="credentials")


class IntegrationInboundConfig(Base):
    """
    Inbound webhook configuration for integrations (INT-003).

    Defines how to receive webhooks from external services,
    authenticate them, and route them to internal services.
    """
    __tablename__ = "integration_inbound_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(String, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, unique=True)
    webhook_path = Column(String(100), nullable=False, unique=True)
    auth_method = Column(
        Enum(InboundAuthMethod, name="inbound_auth_method_enum", create_type=False),
        nullable=False,
        default=InboundAuthMethod.none
    )
    signature_secret = Column(Text, nullable=True)  # Encrypted HMAC secret
    event_filters = Column(JSON, nullable=True)  # List of event types to accept
    transform_template = Column(Text, nullable=True)  # Jinja2 template for payload transformation
    destination_service = Column(
        Enum(DestinationService, name="destination_service_enum", create_type=False),
        nullable=False,
        default=DestinationService.tentackl
    )
    destination_config = Column(JSON, nullable=True)  # URL, headers, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    integration = relationship("Integration", back_populates="inbound_config")


class IntegrationOutboundConfig(Base):
    """
    Outbound action configuration for integrations (INT-004).

    Defines how to send messages/actions to external services,
    with rate limiting and templating support.
    """
    __tablename__ = "integration_outbound_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(String, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, unique=True)
    action_type = Column(
        Enum(OutboundActionType, name="outbound_action_type_enum", create_type=False),
        nullable=False
    )
    default_template = Column(JSON, nullable=True)  # Default message/embed template
    rate_limit_requests = Column(Integer, nullable=True)  # Max requests per window
    rate_limit_window_seconds = Column(Integer, nullable=True)  # Window duration
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    integration = relationship("Integration", back_populates="outbound_config")


class IntegrationWebhookEvent(Base):
    """
    Integration webhook event log (INT-012).

    Records webhooks received via the integration gateway
    for auditing, idempotency, and retry handling.
    """
    __tablename__ = "integration_webhook_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = Column(String, ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(String(50), nullable=False, index=True)
    webhook_path = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    raw_payload = Column(JSON, nullable=False)
    transformed_payload = Column(JSON, nullable=True)
    destination_service = Column(String(50), nullable=False)
    destination_config = Column(JSON, nullable=True)
    status = Column(
        Enum(IntegrationWebhookEventStatus, name="integration_webhook_event_status_enum", create_type=False),
        nullable=False,
        default=IntegrationWebhookEventStatus.received
    )
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    integration = relationship("Integration", back_populates="webhook_events")
    deliveries = relationship("IntegrationWebhookDelivery", back_populates="event", cascade="all, delete-orphan")


class IntegrationWebhookDelivery(Base):
    """
    Integration webhook delivery tracking (INT-012).

    Tracks each attempt to route an integration webhook event
    to downstream services.
    """
    __tablename__ = "integration_webhook_deliveries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("integration_webhook_events.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_service = Column(String(50), nullable=False)
    destination_url = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending, success, failed
    celery_task_id = Column(String(255), nullable=True)
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, default=1)
    last_attempt_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    event = relationship("IntegrationWebhookEvent", back_populates="deliveries")
