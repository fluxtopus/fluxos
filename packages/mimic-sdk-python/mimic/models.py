"""Data models for Mimic SDK."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class IntegrationProvider(str, Enum):
    """Supported integration providers."""

    discord = "discord"
    slack = "slack"
    github = "github"
    stripe = "stripe"
    custom_webhook = "custom_webhook"


class IntegrationDirection(str, Enum):
    """Integration direction."""

    inbound = "inbound"
    outbound = "outbound"
    bidirectional = "bidirectional"


class IntegrationStatus(str, Enum):
    """Integration status."""

    active = "active"
    paused = "paused"
    error = "error"


class CredentialType(str, Enum):
    """Credential types."""

    api_key = "api_key"
    oauth_token = "oauth_token"
    webhook_url = "webhook_url"
    bot_token = "bot_token"
    webhook_secret = "webhook_secret"


class InboundAuthMethod(str, Enum):
    """Inbound webhook authentication methods."""

    api_key = "api_key"
    signature = "signature"
    ed25519 = "ed25519"
    bearer = "bearer"
    none = "none"


class DestinationService(str, Enum):
    """Destination services for inbound webhooks."""

    tentackl = "tentackl"
    custom = "custom"


class OutboundActionType(str, Enum):
    """Outbound action types."""

    send_message = "send_message"
    send_embed = "send_embed"
    send_blocks = "send_blocks"
    create_issue = "create_issue"
    post_comment = "post_comment"
    post = "post"
    put = "put"


# =============================================================================
# Integration Models
# =============================================================================


class IntegrationCreate(BaseModel):
    """Model for creating a new integration."""

    name: str = Field(..., min_length=1, max_length=255, description="User-facing label")
    provider: IntegrationProvider = Field(..., description="Integration provider")
    direction: IntegrationDirection = Field(
        default=IntegrationDirection.bidirectional, description="Integration direction"
    )


class IntegrationUpdate(BaseModel):
    """Model for updating an integration."""

    name: str | None = Field(None, min_length=1, max_length=255)
    direction: IntegrationDirection | None = None
    status: IntegrationStatus | None = None


class CredentialSummary(BaseModel):
    """Summary of an integration credential (no sensitive data)."""

    id: str
    credential_type: str
    has_expiration: bool
    is_expired: bool
    created_at: str


class InboundConfigSummary(BaseModel):
    """Summary of inbound webhook configuration."""

    webhook_path: str
    webhook_url: str
    auth_method: str
    destination_service: str
    is_active: bool


class OutboundConfigSummary(BaseModel):
    """Summary of outbound action configuration."""

    action_type: str
    has_rate_limit: bool
    is_active: bool


class Integration(BaseModel):
    """Integration model."""

    id: str = Field(..., description="Integration ID")
    organization_id: str = Field(..., description="Organization ID")
    user_id: str = Field(..., description="User ID who created the integration")
    name: str = Field(..., description="User-facing label")
    provider: str = Field(..., description="Integration provider")
    direction: str = Field(..., description="Integration direction")
    status: str = Field(..., description="Integration status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class IntegrationDetail(Integration):
    """Detailed integration model with related configurations."""

    credentials: list[CredentialSummary] = Field(default_factory=list)
    inbound_config: InboundConfigSummary | None = None
    outbound_config: OutboundConfigSummary | None = None


class IntegrationListResponse(BaseModel):
    """Response model for listing integrations."""

    items: list[Integration]
    total: int


# =============================================================================
# Credential Models
# =============================================================================


class CredentialCreate(BaseModel):
    """Model for creating a new credential."""

    credential_type: CredentialType = Field(..., description="Type of credential")
    value: str = Field(..., min_length=1, description="Credential value")
    credential_metadata: dict[str, Any] | None = Field(
        None,
        alias="metadata",
        description="Extra fields: from_email, channel_id, etc.",
    )
    expires_at: datetime | None = Field(None, description="Expiration for OAuth tokens")

    model_config = {"populate_by_name": True}


class CredentialUpdate(BaseModel):
    """Model for updating a credential."""

    value: str | None = Field(None, min_length=1, description="New credential value")
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")
    expires_at: datetime | None = Field(None, description="Updated expiration")


class Credential(BaseModel):
    """Credential model (no sensitive data)."""

    id: str
    credential_type: str
    has_value: bool
    metadata: dict[str, Any] | None
    has_expiration: bool
    is_expired: bool
    created_at: str
    updated_at: str


class CredentialTestResult(BaseModel):
    """Result of credential test."""

    success: bool
    message: str


# =============================================================================
# Inbound Config Models
# =============================================================================


class InboundConfigCreate(BaseModel):
    """Model for creating/updating inbound webhook configuration."""

    webhook_path: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="Unique webhook path slug. Auto-generated if not provided.",
    )
    auth_method: InboundAuthMethod = Field(
        default=InboundAuthMethod.none,
        description="Authentication method for incoming webhooks",
    )
    signature_secret: str | None = Field(
        None, description="HMAC secret for signature authentication"
    )
    event_filters: list[str] | None = Field(
        None, description="Array of event types to accept"
    )
    transform_template: str | None = Field(
        None, description="Jinja2 template for payload transformation"
    )
    destination_service: DestinationService = Field(
        default=DestinationService.tentackl, description="Service to route events to"
    )
    destination_config: dict[str, Any] | None = Field(
        None, description="Destination config: task_template_id, workflow_id, webhook_url"
    )
    is_active: bool = Field(default=True, description="Whether this config is active")


class InboundConfig(BaseModel):
    """Inbound webhook configuration model."""

    id: str
    integration_id: str
    webhook_path: str
    webhook_url: str  # Full URL
    auth_method: str
    has_signature_secret: bool
    event_filters: list[str] | None
    transform_template: str | None
    destination_service: str
    destination_config: dict[str, Any] | None
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# Outbound Config Models
# =============================================================================


class OutboundConfigCreate(BaseModel):
    """Model for creating/updating outbound action configuration."""

    action_type: OutboundActionType = Field(
        ..., description="Type of outbound action"
    )
    default_template: dict[str, Any] | None = Field(
        None, description="Default values for action parameters"
    )
    rate_limit_requests: int | None = Field(
        None, ge=1, le=10000, description="Max requests per window"
    )
    rate_limit_window_seconds: int | None = Field(
        None, ge=1, le=86400, description="Rate limit window size"
    )
    is_active: bool = Field(default=True, description="Whether this config is active")


class OutboundConfig(BaseModel):
    """Outbound action configuration model."""

    id: str
    integration_id: str
    action_type: str
    default_template: dict[str, Any] | None
    rate_limit_requests: int | None
    rate_limit_window_seconds: int | None
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# Action Execution Models
# =============================================================================


class ActionExecuteRequest(BaseModel):
    """Request model for executing an outbound action."""

    # Action-specific parameters - merged with default_template
    content: str | None = Field(None, description="Message content")
    title: str | None = Field(None, description="Title for embeds/issues")
    description: str | None = Field(None, description="Description for embeds/issues")
    color: Any | None = Field(None, description="Color for Discord embeds")
    fields: list[dict[str, Any]] | None = Field(None, description="Fields for embeds")
    blocks: list[dict[str, Any]] | None = Field(None, description="Slack Block Kit blocks")
    body: str | None = Field(None, description="Body text for GitHub issues/comments")
    repo: str | None = Field(None, description="GitHub repository (owner/repo)")
    issue_number: int | None = Field(None, description="GitHub issue number")
    labels: list[str] | None = Field(None, description="Labels for GitHub issues")
    url: str | None = Field(None, description="Target URL for webhook actions")
    headers: dict[str, str] | None = Field(None, description="Custom headers")
    payload: dict[str, Any] | None = Field(None, description="Custom payload")
    channel_id: str | None = Field(None, description="Channel ID for Slack/Discord")

    # Discord-specific options
    username: str | None = Field(None, description="Override bot username")
    avatar_url: str | None = Field(None, description="Override bot avatar URL")
    thread_id: str | None = Field(None, description="Discord forum thread ID")

    # Slack-specific options
    channel: str | None = Field(None, description="Slack channel override")
    icon_emoji: str | None = Field(None, description="Slack bot icon emoji")
    thread_ts: str | None = Field(None, description="Slack thread timestamp")

    # Execution options
    async_execution: bool = Field(
        default=False, description="Execute asynchronously"
    )


class ActionExecuteResponse(BaseModel):
    """Response model for action execution."""

    success: bool
    integration_id: str
    action_type: str
    result: dict[str, Any] | None = None
    job_id: str | None = None
    message: str
