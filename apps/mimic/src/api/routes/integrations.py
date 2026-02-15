"""
Integration CRUD routes (INT-005), Credential Management (INT-006), Inbound Config (INT-007),
Outbound Config (INT-008), and Dynamic Webhook Gateway (INT-009).

Provides REST API endpoints for managing integrations:
- POST /api/v1/integrations - Create integration
- GET /api/v1/integrations - List user's integrations
- GET /api/v1/integrations/{id} - Get integration details
- PUT /api/v1/integrations/{id} - Update integration
- DELETE /api/v1/integrations/{id} - Soft delete integration

Credential management (INT-006):
- POST /api/v1/integrations/{id}/credentials - Add credential
- PUT /api/v1/integrations/{id}/credentials/{cred_id} - Update credential
- DELETE /api/v1/integrations/{id}/credentials/{cred_id} - Remove credential
- POST /api/v1/integrations/{id}/credentials/{cred_id}/test - Test credential

Inbound config management (INT-007):
- PUT /api/v1/integrations/{id}/inbound - Set inbound config
- GET /api/v1/integrations/{id}/inbound - Get inbound config
- DELETE /api/v1/integrations/{id}/inbound - Disable/delete inbound config

Outbound config management (INT-008):
- PUT /api/v1/integrations/{id}/outbound - Set outbound config
- GET /api/v1/integrations/{id}/outbound - Get outbound config
- DELETE /api/v1/integrations/{id}/outbound - Disable/delete outbound config

Dynamic Webhook Gateway (INT-009):
- POST /api/v1/gateway/integrations/{webhook_path} - Receive webhooks for integrations

All endpoints require authentication and are scoped to user's organization.
Credentials are never returned in plaintext after creation.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Annotated, Any, Optional, List
import uuid

import redis
import structlog
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from src.api.auth import AuthContext, require_permission
from src.database.database import get_db
from src.database.models import (
    CredentialType,
    DestinationService,
    InboundAuthMethod,
    Integration,
    IntegrationCredential,
    IntegrationDirection,
    IntegrationInboundConfig,
    IntegrationOutboundConfig,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationWebhookEvent,
    IntegrationWebhookDelivery,
    IntegrationWebhookEventStatus,
    OutboundActionType,
)
from src.services.key_encryption import KeyEncryptionService
from src.services.provider_validator import ProviderValidatorService
from src.services.discord_interaction_service import DiscordInteractionService


def get_route_integration_event_task():
    """Lazy import of Celery task to avoid import issues during testing."""
    from src.core.tasks import route_integration_event
    return route_integration_event


# =============================================================================
# Discord Character Limits (INT-014)
# https://discord.com/developers/docs/resources/channel#embed-limits
# =============================================================================
DISCORD_LIMITS = {
    # Message content limit
    "content": 2000,
    # Embed limits
    "embed_title": 256,
    "embed_description": 4096,
    "embed_field_name": 256,
    "embed_field_value": 1024,
    "embed_fields_max": 25,
    "embed_footer_text": 2048,
    "embed_author_name": 256,
    # Total embed limit
    "embed_total": 6000,
}

# =============================================================================
# Slack Character Limits (INT-015)
# https://api.slack.com/reference/surfaces/formatting#basic-formatting
# https://api.slack.com/reference/block-kit/blocks
# =============================================================================
SLACK_LIMITS = {
    # Message text limit
    "text": 40000,
    # Block Kit limits
    "blocks_max": 50,  # Max blocks in a single message
    "block_text": 3000,  # Text in a section/context block
    "block_id": 255,  # block_id length
    # Section block limits
    "section_text": 3000,
    "section_fields_max": 10,
    "section_field_text": 2000,
    # Header block limits
    "header_text": 150,
    # Divider has no text limits
    # Image block limits
    "image_alt_text": 2000,
    "image_title": 2000,
    # Context block limits
    "context_elements_max": 10,
    # Actions block limits
    "actions_elements_max": 25,
    # Input block limits
    "input_label": 2000,
    "input_hint": 150,
    # Button/element limits
    "button_text": 75,
    "button_value": 2000,
    "action_id": 255,
    # Overflow menu limit
    "overflow_options_max": 5,
    # Select menu limits
    "select_options_max": 100,
    "option_text": 75,
    "option_value": 75,
}


logger = structlog.get_logger(__name__)

router = APIRouter()

# Initialize services
encryption_service = KeyEncryptionService()
validator_service = ProviderValidatorService()
discord_interaction_service = DiscordInteractionService()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class IntegrationCreate(BaseModel):
    """Schema for creating a new integration."""

    name: str = Field(..., min_length=1, max_length=255, description="User-facing label")
    provider: IntegrationProvider = Field(..., description="Integration provider")
    direction: IntegrationDirection = Field(
        default=IntegrationDirection.bidirectional, description="Integration direction"
    )


class IntegrationUpdate(BaseModel):
    """Schema for updating an integration."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    direction: Optional[IntegrationDirection] = None
    status: Optional[IntegrationStatus] = None


class IntegrationCredentialSummary(BaseModel):
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


class IntegrationResponse(BaseModel):
    """Response schema for integration."""

    id: str
    organization_id: str
    user_id: str
    name: str
    provider: str
    direction: str
    status: str
    created_at: str
    updated_at: str


class IntegrationDetailResponse(IntegrationResponse):
    """Detailed response schema including related configurations."""

    credentials: List[IntegrationCredentialSummary] = []
    inbound_config: Optional[InboundConfigSummary] = None
    outbound_config: Optional[OutboundConfigSummary] = None


class IntegrationListResponse(BaseModel):
    """Response schema for listing integrations."""

    items: List[IntegrationResponse]
    total: int


# =============================================================================
# Credential Schemas (INT-006)
# =============================================================================


class CredentialCreate(BaseModel):
    """Schema for creating a new credential."""

    credential_type: CredentialType = Field(..., description="Type of credential")
    value: str = Field(..., min_length=1, description="Credential value (will be encrypted)")
    metadata: Optional[dict] = Field(None, description="Extra fields: from_email, channel_id, etc.")
    expires_at: Optional[datetime] = Field(None, description="Expiration for OAuth tokens")


class CredentialUpdate(BaseModel):
    """Schema for updating a credential."""

    value: Optional[str] = Field(None, min_length=1, description="New credential value")
    metadata: Optional[dict] = Field(None, description="Updated metadata")
    expires_at: Optional[datetime] = Field(None, description="Updated expiration")


class CredentialResponse(BaseModel):
    """Response schema for credential (no sensitive data)."""

    id: str
    credential_type: str
    has_value: bool
    metadata: Optional[dict]
    has_expiration: bool
    is_expired: bool
    created_at: str
    updated_at: str


class CredentialTestResponse(BaseModel):
    """Response schema for credential test."""

    success: bool
    message: str


# =============================================================================
# Inbound Config Schemas (INT-007)
# =============================================================================

# Base webhook URL - configurable via environment variable
MIMIC_BASE_WEBHOOK_URL = os.environ.get(
    "MIMIC_BASE_WEBHOOK_URL",
    "https://mimic.fluxtopus.com/api/v1/gateway/integrations"
)


class InboundConfigCreate(BaseModel):
    """Schema for creating/updating inbound webhook configuration."""

    webhook_path: Optional[str] = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="Unique webhook path slug. Auto-generated if not provided."
    )
    auth_method: InboundAuthMethod = Field(
        default=InboundAuthMethod.none,
        description="Authentication method for incoming webhooks"
    )
    signature_secret: Optional[str] = Field(
        None,
        description="HMAC secret for signature authentication (will be encrypted)"
    )
    event_filters: Optional[List[str]] = Field(
        None,
        description="Array of event types to accept (empty = all events)"
    )
    transform_template: Optional[str] = Field(
        None,
        description="Jinja2 template for payload transformation"
    )
    destination_service: DestinationService = Field(
        default=DestinationService.tentackl,
        description="Service to route events to"
    )
    destination_config: Optional[dict] = Field(
        None,
        description="Destination configuration: task_template_id, workflow_id, or webhook_url"
    )
    is_active: bool = Field(
        default=True,
        description="Whether this inbound config is active"
    )


class InboundConfigResponse(BaseModel):
    """Response schema for inbound webhook configuration."""

    id: str
    integration_id: str
    webhook_path: str
    webhook_url: str  # Full URL: https://mimic.fluxtopus.com/api/v1/gateway/integrations/{webhook_path}
    auth_method: str
    has_signature_secret: bool
    event_filters: Optional[List[str]]
    transform_template: Optional[str]
    destination_service: str
    destination_config: Optional[dict]
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# Outbound Config Schemas (INT-008)
# =============================================================================


# Mapping of provider to supported action types
PROVIDER_ACTION_TYPES: dict[str, set[str]] = {
    "discord": {"send_message", "send_embed"},
    "slack": {"send_message", "send_blocks"},
    "github": {"create_issue", "post_comment"},
    "stripe": set(),  # Stripe is typically inbound only
    "twitter": {"send_message"},
    "custom_webhook": {"post", "put", "send_message"},
}


class OutboundConfigCreate(BaseModel):
    """Schema for creating/updating outbound action configuration."""

    action_type: OutboundActionType = Field(
        ...,
        description="Type of outbound action (must be supported by the provider)"
    )
    default_template: Optional[dict] = Field(
        None,
        description="Default values for action parameters (e.g., default message content)"
    )
    rate_limit_requests: Optional[int] = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of requests per rate limit window"
    )
    rate_limit_window_seconds: Optional[int] = Field(
        None,
        ge=1,
        le=86400,
        description="Rate limit window size in seconds (max 24 hours)"
    )
    is_active: bool = Field(
        default=True,
        description="Whether this outbound config is active"
    )


class OutboundConfigResponse(BaseModel):
    """Response schema for outbound action configuration."""

    id: str
    integration_id: str
    action_type: str
    default_template: Optional[dict]
    rate_limit_requests: Optional[int]
    rate_limit_window_seconds: Optional[int]
    is_active: bool
    created_at: str
    updated_at: str


# =============================================================================
# Helper Functions
# =============================================================================


def _integration_to_response(integration: Integration) -> IntegrationResponse:
    """Convert Integration model to response schema."""
    return IntegrationResponse(
        id=integration.id,
        organization_id=integration.organization_id,
        user_id=integration.user_id,
        name=integration.name,
        provider=integration.provider.value,
        direction=integration.direction.value,
        status=integration.status.value,
        created_at=integration.created_at.isoformat() if integration.created_at else "",
        updated_at=integration.updated_at.isoformat() if integration.updated_at else "",
    )


def _integration_to_detail_response(
    integration: Integration, base_webhook_url: str = "https://mimic.fluxtopus.com/api/v1/gateway/integrations"
) -> IntegrationDetailResponse:
    """Convert Integration model to detailed response schema."""
    now = datetime.utcnow()

    credentials = []
    for cred in integration.credentials:
        is_expired = cred.expires_at is not None and cred.expires_at < now
        credentials.append(
            IntegrationCredentialSummary(
                id=cred.id,
                credential_type=cred.credential_type.value,
                has_expiration=cred.expires_at is not None,
                is_expired=is_expired,
                created_at=cred.created_at.isoformat() if cred.created_at else "",
            )
        )

    inbound_config = None
    if integration.inbound_config:
        ic = integration.inbound_config
        inbound_config = InboundConfigSummary(
            webhook_path=ic.webhook_path,
            webhook_url=f"{base_webhook_url}/{ic.webhook_path}",
            auth_method=ic.auth_method.value,
            destination_service=ic.destination_service.value,
            is_active=ic.is_active,
        )

    outbound_config = None
    if integration.outbound_config:
        oc = integration.outbound_config
        outbound_config = OutboundConfigSummary(
            action_type=oc.action_type.value,
            has_rate_limit=oc.rate_limit_requests is not None,
            is_active=oc.is_active,
        )

    return IntegrationDetailResponse(
        id=integration.id,
        organization_id=integration.organization_id,
        user_id=integration.user_id,
        name=integration.name,
        provider=integration.provider.value,
        direction=integration.direction.value,
        status=integration.status.value,
        created_at=integration.created_at.isoformat() if integration.created_at else "",
        updated_at=integration.updated_at.isoformat() if integration.updated_at else "",
        credentials=credentials,
        inbound_config=inbound_config,
        outbound_config=outbound_config,
    )


def _get_integration_or_404(
    db: Session, integration_id: str, organization_id: str, load_relations: bool = False
) -> Integration:
    """Get integration by ID and organization, or raise 404."""
    query = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == organization_id,
        Integration.deleted_at.is_(None),
    )

    if load_relations:
        query = query.options(
            joinedload(Integration.credentials),
            joinedload(Integration.inbound_config),
            joinedload(Integration.outbound_config),
        )

    integration = query.first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    return integration


def _get_credential_or_404(
    db: Session, integration: Integration, credential_id: str
) -> IntegrationCredential:
    """Get credential by ID within an integration, or raise 404."""
    credential = db.query(IntegrationCredential).filter(
        IntegrationCredential.id == credential_id,
        IntegrationCredential.integration_id == integration.id,
    ).first()

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential {credential_id} not found",
        )

    return credential


def _credential_to_response(credential: IntegrationCredential) -> CredentialResponse:
    """Convert IntegrationCredential model to response schema (no sensitive data)."""
    now = datetime.utcnow()
    is_expired = credential.expires_at is not None and credential.expires_at < now

    return CredentialResponse(
        id=credential.id,
        credential_type=credential.credential_type.value,
        has_value=bool(credential.encrypted_value),
        metadata=credential.credential_metadata,
        has_expiration=credential.expires_at is not None,
        is_expired=is_expired,
        created_at=credential.created_at.isoformat() if credential.created_at else "",
        updated_at=credential.updated_at.isoformat() if credential.updated_at else "",
    )


def _inbound_config_to_response(
    inbound_config: IntegrationInboundConfig,
    base_webhook_url: str = None,
) -> InboundConfigResponse:
    """Convert IntegrationInboundConfig model to response schema."""
    if base_webhook_url is None:
        base_webhook_url = MIMIC_BASE_WEBHOOK_URL

    return InboundConfigResponse(
        id=inbound_config.id,
        integration_id=inbound_config.integration_id,
        webhook_path=inbound_config.webhook_path,
        webhook_url=f"{base_webhook_url}/{inbound_config.webhook_path}",
        auth_method=inbound_config.auth_method.value,
        has_signature_secret=bool(inbound_config.signature_secret),
        event_filters=inbound_config.event_filters,
        transform_template=inbound_config.transform_template,
        destination_service=inbound_config.destination_service.value,
        destination_config=inbound_config.destination_config,
        is_active=inbound_config.is_active,
        created_at=inbound_config.created_at.isoformat() if inbound_config.created_at else "",
        updated_at=inbound_config.updated_at.isoformat() if inbound_config.updated_at else "",
    )


def _generate_webhook_path() -> str:
    """Generate a unique webhook path slug."""
    return f"wh-{secrets.token_urlsafe(12).lower()}"


def _get_inbound_config_or_404(db: Session, integration: Integration) -> IntegrationInboundConfig:
    """Get inbound config for an integration, or raise 404."""
    if not integration.inbound_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inbound config not found for integration {integration.id}",
        )
    return integration.inbound_config


def _outbound_config_to_response(
    outbound_config: IntegrationOutboundConfig,
) -> OutboundConfigResponse:
    """Convert IntegrationOutboundConfig model to response schema."""
    return OutboundConfigResponse(
        id=outbound_config.id,
        integration_id=outbound_config.integration_id,
        action_type=outbound_config.action_type.value,
        default_template=outbound_config.default_template,
        rate_limit_requests=outbound_config.rate_limit_requests,
        rate_limit_window_seconds=outbound_config.rate_limit_window_seconds,
        is_active=outbound_config.is_active,
        created_at=outbound_config.created_at.isoformat() if outbound_config.created_at else "",
        updated_at=outbound_config.updated_at.isoformat() if outbound_config.updated_at else "",
    )


def _get_outbound_config_or_404(db: Session, integration: Integration) -> IntegrationOutboundConfig:
    """Get outbound config for an integration, or raise 404."""
    if not integration.outbound_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outbound config not found for integration {integration.id}",
        )
    return integration.outbound_config


def _validate_action_type_for_provider(provider: IntegrationProvider, action_type: OutboundActionType) -> None:
    """Validate that the action_type is supported by the provider."""
    provider_value = provider.value
    supported_actions = PROVIDER_ACTION_TYPES.get(provider_value, set())

    if not supported_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider_value}' does not support outbound actions",
        )

    if action_type.value not in supported_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action type '{action_type.value}' is not supported for provider '{provider_value}'. "
                   f"Supported actions: {', '.join(sorted(supported_actions))}",
        )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/integrations", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    data: IntegrationCreate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "create"))],
    db: Session = Depends(get_db),
):
    """
    Create a new integration.

    Creates an integration for the user's organization with the specified
    provider and direction. The integration starts in 'active' status.
    """
    integration = Integration(
        id=str(uuid.uuid4()),
        organization_id=auth.organization_id,
        user_id=auth.user_id,
        name=data.name,
        provider=data.provider,
        direction=data.direction,
        status=IntegrationStatus.active,
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    logger.info(
        "integration_created",
        integration_id=integration.id,
        organization_id=auth.organization_id,
        provider=data.provider.value,
    )

    return _integration_to_response(integration)


@router.get("/integrations", response_model=IntegrationListResponse)
async def list_integrations(
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
    provider: Optional[IntegrationProvider] = Query(None, description="Filter by provider"),
    status_filter: Optional[IntegrationStatus] = Query(None, alias="status", description="Filter by status"),
    direction: Optional[IntegrationDirection] = Query(None, description="Filter by direction"),
    limit: int = Query(100, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
):
    """
    List integrations for the user's organization.

    Returns all non-deleted integrations scoped to the organization.
    Supports filtering by provider, status, and direction.
    """
    query = db.query(Integration).filter(
        Integration.organization_id == auth.organization_id,
        Integration.deleted_at.is_(None),
    )

    if provider:
        query = query.filter(Integration.provider == provider)
    if status_filter:
        query = query.filter(Integration.status == status_filter)
    if direction:
        query = query.filter(Integration.direction == direction)

    total = query.count()
    integrations = query.order_by(Integration.created_at.desc()).offset(offset).limit(limit).all()

    return IntegrationListResponse(
        items=[_integration_to_response(i) for i in integrations],
        total=total,
    )


@router.get("/integrations/{integration_id}", response_model=IntegrationDetailResponse)
async def get_integration(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
):
    """
    Get integration details.

    Returns the integration with its credentials (summary only, no sensitive data),
    inbound configuration, and outbound configuration.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    return _integration_to_detail_response(integration)


@router.put("/integrations/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    data: IntegrationUpdate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Update an integration.

    Allows updating the name, direction, and status. Provider cannot be changed
    after creation.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)

    if data.name is not None:
        integration.name = data.name
    if data.direction is not None:
        integration.direction = data.direction
    if data.status is not None:
        integration.status = data.status

    db.commit()
    db.refresh(integration)

    logger.info(
        "integration_updated",
        integration_id=integration.id,
        organization_id=auth.organization_id,
    )

    return _integration_to_response(integration)


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "delete"))],
    db: Session = Depends(get_db),
):
    """
    Soft delete an integration.

    Sets deleted_at timestamp. Related credentials, inbound config, and outbound
    config are cascade deleted by the database.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)

    # Soft delete
    integration.deleted_at = datetime.utcnow()
    db.commit()

    logger.info(
        "integration_deleted",
        integration_id=integration.id,
        organization_id=auth.organization_id,
    )

    return None


# =============================================================================
# Credential Management Endpoints (INT-006)
# =============================================================================


@router.post(
    "/integrations/{integration_id}/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    integration_id: str,
    data: CredentialCreate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Add a credential to an integration.

    The credential value is encrypted before storage and will never be
    returned in plaintext after creation. Multiple credentials of different
    types can be added to a single integration.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)

    # Encrypt the credential value
    encrypted_value = encryption_service.encrypt(data.value)

    credential = IntegrationCredential(
        id=str(uuid.uuid4()),
        integration_id=integration.id,
        credential_type=data.credential_type,
        encrypted_value=encrypted_value,
        credential_metadata=data.metadata,
        expires_at=data.expires_at,
    )

    db.add(credential)
    db.commit()
    db.refresh(credential)

    logger.info(
        "credential_created",
        credential_id=credential.id,
        integration_id=integration.id,
        credential_type=data.credential_type.value,
        organization_id=auth.organization_id,
    )

    return _credential_to_response(credential)


@router.get(
    "/integrations/{integration_id}/credentials",
    response_model=List[CredentialResponse],
)
async def list_credentials(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
):
    """
    List all credentials for an integration.

    Returns credential summaries without sensitive data. The actual credential
    values are never exposed.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    return [_credential_to_response(cred) for cred in integration.credentials]


@router.put(
    "/integrations/{integration_id}/credentials/{credential_id}",
    response_model=CredentialResponse,
)
async def update_credential(
    integration_id: str,
    credential_id: str,
    data: CredentialUpdate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Update a credential.

    If a new value is provided, it will be encrypted before storage.
    The credential type cannot be changed after creation.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)
    credential = _get_credential_or_404(db, integration, credential_id)

    if data.value is not None:
        credential.encrypted_value = encryption_service.encrypt(data.value)

    if data.metadata is not None:
        credential.credential_metadata = data.metadata

    if data.expires_at is not None:
        credential.expires_at = data.expires_at

    db.commit()
    db.refresh(credential)

    logger.info(
        "credential_updated",
        credential_id=credential.id,
        integration_id=integration.id,
        organization_id=auth.organization_id,
    )

    return _credential_to_response(credential)


@router.delete(
    "/integrations/{integration_id}/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_credential(
    integration_id: str,
    credential_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Remove a credential from an integration.

    This is a hard delete - the credential is permanently removed.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)
    credential = _get_credential_or_404(db, integration, credential_id)

    db.delete(credential)
    db.commit()

    logger.info(
        "credential_deleted",
        credential_id=credential_id,
        integration_id=integration.id,
        organization_id=auth.organization_id,
    )

    return None


@router.post(
    "/integrations/{integration_id}/credentials/{credential_id}/test",
    response_model=CredentialTestResponse,
)
async def test_credential(
    integration_id: str,
    credential_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Test a credential by calling the external service.

    Decrypts the credential and validates it works by making a test call
    to the provider. The result indicates whether the credential is valid.
    """
    integration = _get_integration_or_404(db, integration_id, auth.organization_id)
    credential = _get_credential_or_404(db, integration, credential_id)

    # Decrypt the credential value
    try:
        decrypted_value = encryption_service.decrypt(credential.encrypted_value)
    except Exception as e:
        logger.error(
            "credential_decrypt_failed",
            credential_id=credential.id,
            error=str(e),
        )
        return CredentialTestResponse(
            success=False,
            message="Failed to decrypt credential",
        )

    # Map credential type to provider validator parameters
    cred_type = credential.credential_type
    provider = integration.provider.value

    try:
        # Route to appropriate validator based on credential type and provider
        success = False

        if cred_type == CredentialType.webhook_url:
            # Validate webhook URL based on provider
            if provider == "discord":
                success = await validator_service._validate_discord(decrypted_value)
            elif provider == "slack":
                success = await validator_service._validate_slack(decrypted_value)
            else:
                success = await validator_service._validate_webhook(decrypted_value)

        elif cred_type == CredentialType.api_key:
            # Validate API key based on provider
            if provider == "github":
                # GitHub API key validation
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        "https://api.github.com/user",
                        headers={"Authorization": f"Bearer {decrypted_value}"},
                        timeout=5.0,
                    )
                    success = response.status_code == 200
            elif provider == "stripe":
                # Stripe API key validation
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        "https://api.stripe.com/v1/balance",
                        auth=(decrypted_value, ""),
                        timeout=5.0,
                    )
                    success = response.status_code == 200
            else:
                # Generic: assume valid if non-empty
                success = bool(decrypted_value)

        elif cred_type == CredentialType.bot_token:
            # Validate bot token based on provider
            if provider == "discord":
                # Discord bot token validation
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        "https://discord.com/api/v10/users/@me",
                        headers={"Authorization": f"Bot {decrypted_value}"},
                        timeout=5.0,
                    )
                    success = response.status_code == 200
            elif provider == "slack":
                # Slack bot token validation
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://slack.com/api/auth.test",
                        headers={"Authorization": f"Bearer {decrypted_value}"},
                        timeout=5.0,
                    )
                    data = response.json()
                    success = response.status_code == 200 and data.get("ok", False)
            else:
                success = bool(decrypted_value)

        elif cred_type == CredentialType.oauth_token:
            # OAuth tokens are typically validated by the OAuth flow itself
            # For now, just verify it's non-empty and not expired
            if credential.expires_at:
                success = credential.expires_at > datetime.utcnow() and bool(decrypted_value)
            else:
                success = bool(decrypted_value)

        elif cred_type == CredentialType.webhook_secret:
            # Webhook secrets can't be "tested" - they're for signature validation
            # Just verify it exists
            success = bool(decrypted_value)

        else:
            success = bool(decrypted_value)

        if success:
            logger.info(
                "credential_test_success",
                credential_id=credential.id,
                integration_id=integration.id,
                credential_type=cred_type.value,
                provider=provider,
            )
            return CredentialTestResponse(
                success=True,
                message=f"Credential test successful for {provider} {cred_type.value}",
            )
        else:
            logger.warning(
                "credential_test_failed",
                credential_id=credential.id,
                integration_id=integration.id,
                credential_type=cred_type.value,
                provider=provider,
            )
            return CredentialTestResponse(
                success=False,
                message=f"Credential test failed for {provider} {cred_type.value}",
            )

    except Exception as e:
        logger.error(
            "credential_test_error",
            credential_id=credential.id,
            integration_id=integration.id,
            error=str(e),
        )
        return CredentialTestResponse(
            success=False,
            message=f"Error testing credential: {str(e)}",
        )


# =============================================================================
# Inbound Config Endpoints (INT-007)
# =============================================================================


@router.put(
    "/integrations/{integration_id}/inbound",
    response_model=InboundConfigResponse,
)
async def set_inbound_config(
    integration_id: str,
    data: InboundConfigCreate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Set (create or update) inbound webhook configuration.

    Creates a new inbound config or updates an existing one for the integration.
    If webhook_path is not provided, a unique path is auto-generated.

    Returns the configuration including the full webhook URL:
    https://mimic.fluxtopus.com/api/v1/gateway/integrations/{webhook_path}
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    # Check if integration supports inbound webhooks
    if integration.direction == IntegrationDirection.outbound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot configure inbound webhooks for outbound-only integration",
        )

    # Generate webhook_path if not provided
    webhook_path = data.webhook_path or _generate_webhook_path()

    # Check for webhook_path uniqueness (excluding current integration's config)
    existing = db.query(IntegrationInboundConfig).filter(
        IntegrationInboundConfig.webhook_path == webhook_path,
        IntegrationInboundConfig.integration_id != integration.id,
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Webhook path '{webhook_path}' is already in use",
        )

    # Encrypt signature_secret if provided
    encrypted_secret = None
    if data.signature_secret:
        encrypted_secret = encryption_service.encrypt(data.signature_secret)

    if integration.inbound_config:
        # Update existing config
        config = integration.inbound_config
        config.webhook_path = webhook_path
        config.auth_method = data.auth_method
        if data.signature_secret is not None:
            config.signature_secret = encrypted_secret
        config.event_filters = data.event_filters
        config.transform_template = data.transform_template
        config.destination_service = data.destination_service
        config.destination_config = data.destination_config
        config.is_active = data.is_active

        logger.info(
            "inbound_config_updated",
            integration_id=integration.id,
            webhook_path=webhook_path,
            organization_id=auth.organization_id,
        )
    else:
        # Create new config
        config = IntegrationInboundConfig(
            id=str(uuid.uuid4()),
            integration_id=integration.id,
            webhook_path=webhook_path,
            auth_method=data.auth_method,
            signature_secret=encrypted_secret,
            event_filters=data.event_filters,
            transform_template=data.transform_template,
            destination_service=data.destination_service,
            destination_config=data.destination_config,
            is_active=data.is_active,
        )
        db.add(config)

        logger.info(
            "inbound_config_created",
            integration_id=integration.id,
            webhook_path=webhook_path,
            organization_id=auth.organization_id,
        )

    db.commit()
    db.refresh(config)

    return _inbound_config_to_response(config)


@router.get(
    "/integrations/{integration_id}/inbound",
    response_model=InboundConfigResponse,
)
async def get_inbound_config(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
):
    """
    Get inbound webhook configuration for an integration.

    Returns the configuration including the full webhook URL.
    Returns 404 if no inbound config exists.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    config = _get_inbound_config_or_404(db, integration)

    return _inbound_config_to_response(config)


@router.delete(
    "/integrations/{integration_id}/inbound",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_inbound_config(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Delete (disable) inbound webhook configuration.

    Permanently removes the inbound config. The webhook URL will no longer
    accept requests after deletion.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    config = _get_inbound_config_or_404(db, integration)

    webhook_path = config.webhook_path
    db.delete(config)
    db.commit()

    logger.info(
        "inbound_config_deleted",
        integration_id=integration.id,
        webhook_path=webhook_path,
        organization_id=auth.organization_id,
    )

    return None


# =============================================================================
# Inbound Config Test Endpoint
# =============================================================================


class InboundConfigTestResponse(BaseModel):
    """Response model for inbound config validation."""
    success: bool
    message: str
    checks: List[dict]


@router.post(
    "/integrations/{integration_id}/inbound/test",
    response_model=InboundConfigTestResponse,
)
async def test_inbound_config(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
):
    """
    Test/validate inbound webhook configuration.

    Validates that the stored credentials and keys are well-formed.
    For ed25519: validates the public key is a parseable Ed25519 key.
    For signature: validates that a signature_secret exists.
    For api_key/bearer: validates that relevant credentials exist.
    For none: always passes.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )
    config = _get_inbound_config_or_404(db, integration)

    checks: List[dict] = []
    all_passed = True

    if config.auth_method == InboundAuthMethod.ed25519:
        if not config.signature_secret:
            checks.append({"name": "public_key_present", "passed": False})
            all_passed = False
        else:
            checks.append({"name": "public_key_present", "passed": True})
            try:
                decrypted_key = encryption_service.decrypt(config.signature_secret)
                valid = discord_interaction_service.validate_public_key(decrypted_key)
                checks.append({"name": "public_key_format", "passed": valid})
                if not valid:
                    all_passed = False
            except Exception:
                checks.append({"name": "public_key_format", "passed": False})
                all_passed = False

    elif config.auth_method == InboundAuthMethod.signature:
        has_secret = bool(config.signature_secret)
        checks.append({"name": "signature_secret_present", "passed": has_secret})
        if not has_secret:
            all_passed = False

    elif config.auth_method in (InboundAuthMethod.api_key, InboundAuthMethod.bearer):
        has_creds = len(integration.credentials) > 0
        checks.append({"name": "credentials_present", "passed": has_creds})
        if not has_creds:
            all_passed = False

    elif config.auth_method == InboundAuthMethod.none:
        checks.append({"name": "no_auth_required", "passed": True})

    message = "All checks passed" if all_passed else "Some checks failed"
    return InboundConfigTestResponse(
        success=all_passed,
        message=message,
        checks=checks,
    )


# =============================================================================
# Outbound Config Endpoints (INT-008)
# =============================================================================


@router.put(
    "/integrations/{integration_id}/outbound",
    response_model=OutboundConfigResponse,
)
async def set_outbound_config(
    integration_id: str,
    data: OutboundConfigCreate,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Set (create or update) outbound action configuration.

    Creates a new outbound config or updates an existing one for the integration.
    Validates that the action_type is supported by the integration's provider.

    **Provider-supported action types:**
    - discord: send_message, send_embed
    - slack: send_message, send_blocks
    - github: create_issue, post_comment
    - custom_webhook: post, put, send_message
    - stripe: No outbound actions supported
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    # Check if integration supports outbound actions
    if integration.direction == IntegrationDirection.inbound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot configure outbound actions for inbound-only integration",
        )

    # Validate action_type is supported by provider
    _validate_action_type_for_provider(integration.provider, data.action_type)

    if integration.outbound_config:
        # Update existing config
        config = integration.outbound_config
        config.action_type = data.action_type
        config.default_template = data.default_template
        config.rate_limit_requests = data.rate_limit_requests
        config.rate_limit_window_seconds = data.rate_limit_window_seconds
        config.is_active = data.is_active

        logger.info(
            "outbound_config_updated",
            integration_id=integration.id,
            action_type=data.action_type.value,
            organization_id=auth.organization_id,
        )
    else:
        # Create new config
        config = IntegrationOutboundConfig(
            id=str(uuid.uuid4()),
            integration_id=integration.id,
            action_type=data.action_type,
            default_template=data.default_template,
            rate_limit_requests=data.rate_limit_requests,
            rate_limit_window_seconds=data.rate_limit_window_seconds,
            is_active=data.is_active,
        )
        db.add(config)

        logger.info(
            "outbound_config_created",
            integration_id=integration.id,
            action_type=data.action_type.value,
            organization_id=auth.organization_id,
        )

    db.commit()
    db.refresh(config)

    return _outbound_config_to_response(config)


@router.get(
    "/integrations/{integration_id}/outbound",
    response_model=OutboundConfigResponse,
)
async def get_outbound_config(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "view"))],
    db: Session = Depends(get_db),
):
    """
    Get outbound action configuration for an integration.

    Returns 404 if no outbound config exists.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    config = _get_outbound_config_or_404(db, integration)

    return _outbound_config_to_response(config)


@router.delete(
    "/integrations/{integration_id}/outbound",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_outbound_config(
    integration_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Delete (disable) outbound action configuration.

    Permanently removes the outbound config. Outbound actions will no longer
    be available for this integration after deletion.
    """
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    config = _get_outbound_config_or_404(db, integration)

    action_type = config.action_type.value
    db.delete(config)
    db.commit()

    logger.info(
        "outbound_config_deleted",
        integration_id=integration.id,
        action_type=action_type,
        organization_id=auth.organization_id,
    )

    return None


# =============================================================================
# Dynamic Integration Webhook Gateway (INT-009)
# =============================================================================

# Create a separate router for the gateway endpoints (no authentication required)
gateway_router = APIRouter(prefix="/gateway/integrations", tags=["integration-gateway"])


class WebhookResponse(BaseModel):
    """Response schema for successful webhook receipt with transformed payload (INT-011)."""

    received: bool = True
    webhook_path: str
    integration_id: str
    provider: str
    message: str = "Webhook received successfully"
    # Transformed payload in standard format (INT-011)
    event_type: str
    timestamp: str
    source: str
    data: Any


class WebhookErrorResponse(BaseModel):
    """Response schema for webhook errors."""

    error: str
    message: str


def _verify_api_key_auth(
    inbound_config: IntegrationInboundConfig,
    api_key_header: Optional[str],
) -> bool:
    """Verify X-API-Key authentication."""
    if not api_key_header:
        return False

    # Get the expected API key from credentials
    integration = inbound_config.integration
    for cred in integration.credentials:
        if cred.credential_type == CredentialType.api_key:
            try:
                decrypted_key = encryption_service.decrypt(cred.encrypted_value)
                if decrypted_key == api_key_header:
                    return True
            except Exception:
                continue
    return False


def _verify_signature_auth(
    inbound_config: IntegrationInboundConfig,
    body: bytes,
    signature_header: Optional[str],
    hub_signature_header: Optional[str],
) -> bool:
    """
    Verify HMAC signature authentication.

    Supports both X-Signature and X-Hub-Signature-256 headers.
    """
    if not inbound_config.signature_secret:
        return False

    # Get the signature to verify
    signature = signature_header or hub_signature_header
    if not signature:
        return False

    try:
        decrypted_secret = encryption_service.decrypt(inbound_config.signature_secret)
    except Exception:
        return False

    # Handle GitHub-style signature with "sha256=" prefix
    expected_prefix = "sha256="
    if signature.startswith(expected_prefix):
        signature = signature[len(expected_prefix):]

    # Compute HMAC-SHA256
    computed = hmac.new(
        decrypted_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(computed.lower(), signature.lower())


def _verify_bearer_auth(
    inbound_config: IntegrationInboundConfig,
    authorization_header: Optional[str],
) -> bool:
    """Verify Authorization: Bearer token authentication."""
    if not authorization_header:
        return False

    # Extract token from "Bearer <token>"
    if not authorization_header.startswith("Bearer "):
        return False

    token = authorization_header[7:]  # len("Bearer ") = 7

    # Check against credentials
    integration = inbound_config.integration
    for cred in integration.credentials:
        # Check against oauth_token, bot_token, or api_key
        if cred.credential_type in [
            CredentialType.oauth_token,
            CredentialType.bot_token,
            CredentialType.api_key,
        ]:
            try:
                decrypted_value = encryption_service.decrypt(cred.encrypted_value)
                if decrypted_value == token:
                    return True
            except Exception:
                continue
    return False


# =============================================================================
# Payload Transformation (INT-011)
# =============================================================================

# Create a sandboxed Jinja2 environment for template rendering
_jinja_env = Environment(loader=BaseLoader(), autoescape=True)


class TransformedPayload(BaseModel):
    """Standard output format for transformed webhook payloads (INT-011)."""

    event_type: str
    timestamp: str
    source: str
    provider: str
    data: Any


def _transform_payload(
    inbound_config: IntegrationInboundConfig,
    raw_payload: dict,
    provider: str,
) -> TransformedPayload:
    """
    Transform an incoming webhook payload using Jinja2 template if configured.

    If transform_template is set, applies the Jinja2 transformation.
    If no template, passes raw payload in data field.
    Transformation errors are logged but don't fail the request.

    Output standard format:
    - event_type: Type of event (from template or 'webhook')
    - timestamp: ISO8601 UTC timestamp
    - source: Webhook path (source identifier)
    - provider: Integration provider
    - data: Transformed or raw payload data
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    source = inbound_config.webhook_path

    # Default values for when no template or template fails
    default_event_type = "webhook"
    default_data = raw_payload

    # If no transform_template, return raw payload in standard format
    if not inbound_config.transform_template:
        logger.debug(
            "webhook_no_transform_template",
            webhook_path=source,
            provider=provider,
        )
        return TransformedPayload(
            event_type=default_event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=default_data,
        )

    # Apply Jinja2 transformation
    try:
        template = _jinja_env.from_string(inbound_config.transform_template)

        # Render the template with the raw payload as context
        # The template can access payload fields directly, e.g., {{ action }} or {{ payload.action }}
        rendered = template.render(
            payload=raw_payload,
            **raw_payload,  # Also expose top-level fields directly
            provider=provider,
            source=source,
            timestamp=timestamp,
        )

        # Parse the rendered output as JSON
        transformed = json.loads(rendered)

        # Extract event_type from transformed data if present, otherwise use default
        event_type = transformed.pop("event_type", default_event_type)

        # The rest of the transformed data goes into the data field
        data = transformed.get("data", transformed)

        logger.info(
            "webhook_payload_transformed",
            webhook_path=source,
            provider=provider,
            event_type=event_type,
        )

        return TransformedPayload(
            event_type=event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=data,
        )

    except TemplateSyntaxError as e:
        # Log template syntax errors but don't fail the request
        logger.error(
            "webhook_transform_template_syntax_error",
            webhook_path=source,
            provider=provider,
            error=str(e),
            line=e.lineno,
        )
        return TransformedPayload(
            event_type=default_event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=default_data,
        )

    except UndefinedError as e:
        # Log undefined variable errors but don't fail the request
        logger.error(
            "webhook_transform_undefined_error",
            webhook_path=source,
            provider=provider,
            error=str(e),
        )
        return TransformedPayload(
            event_type=default_event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=default_data,
        )

    except json.JSONDecodeError as e:
        # Log JSON parse errors but don't fail the request
        logger.error(
            "webhook_transform_json_error",
            webhook_path=source,
            provider=provider,
            error=str(e),
        )
        return TransformedPayload(
            event_type=default_event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=default_data,
        )

    except Exception as e:
        # Log any other errors but don't fail the request
        logger.error(
            "webhook_transform_error",
            webhook_path=source,
            provider=provider,
            error=str(e),
            error_type=type(e).__name__,
        )
        return TransformedPayload(
            event_type=default_event_type,
            timestamp=timestamp,
            source=source,
            provider=provider,
            data=default_data,
        )


def _get_inbound_config_by_webhook_path(
    db: Session, webhook_path: str
) -> Optional[IntegrationInboundConfig]:
    """Look up inbound config by webhook path, including integration for auth."""
    return (
        db.query(IntegrationInboundConfig)
        .options(
            joinedload(IntegrationInboundConfig.integration).joinedload(
                Integration.credentials
            )
        )
        .filter(IntegrationInboundConfig.webhook_path == webhook_path)
        .first()
    )


@gateway_router.post(
    "/{webhook_path}",
    responses={
        200: {"description": "Webhook received successfully"},
        401: {"description": "Authentication failed", "model": WebhookErrorResponse},
        404: {"description": "Webhook not found or inactive", "model": WebhookErrorResponse},
    },
    summary="Receive integration webhook",
    description="""
    Dynamic webhook endpoint for integration webhooks.

    Looks up the integration by webhook_path, validates the request using the
    configured auth_method, and returns success or appropriate error codes.

    **Authentication Methods:**
    - `none`: No authentication required
    - `api_key`: Requires X-API-Key header matching a stored credential
    - `signature`: Requires X-Signature or X-Hub-Signature-256 header with HMAC-SHA256
    - `ed25519`: Requires X-Signature-Ed25519 + X-Signature-Timestamp headers (Discord interactions)
    - `bearer`: Requires Authorization: Bearer token header

    **Response Codes:**
    - 200: Webhook received successfully
    - 401: Authentication failed
    - 404: Webhook path not found or integration inactive
    """,
)
async def receive_integration_webhook(
    webhook_path: str,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_signature_ed25519: Optional[str] = Header(None, alias="X-Signature-Ed25519"),
    x_signature_timestamp: Optional[str] = Header(None, alias="X-Signature-Timestamp"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Receive a webhook for an integration.

    This endpoint handles all inbound webhooks for integrations configured
    through the Integration Management API. It:

    1. Looks up the integration by webhook_path
    2. Validates the integration is active
    3. Authenticates the request using the configured auth_method
    4. Transforms the payload using Jinja2 template if configured (INT-011)
    5. Returns success with transformed payload in standard format

    **Payload Transformation (INT-011):**
    - If transform_template is set, applies Jinja2 transformation
    - If no template, passes raw payload in data field
    - Transformation errors are logged but don't fail the request

    **Standard output format:**
    - event_type: Type of event (from template or 'webhook')
    - timestamp: ISO8601 UTC timestamp
    - source: Webhook path
    - provider: Integration provider
    - data: Transformed or raw payload data

    Note: Event routing (INT-012) will be implemented in subsequent requirements.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Look up inbound config by webhook_path
    inbound_config = _get_inbound_config_by_webhook_path(db, webhook_path)

    # 404: Not found
    if not inbound_config:
        logger.warning(
            "webhook_not_found",
            webhook_path=webhook_path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Webhook not found"},
        )

    integration = inbound_config.integration

    # 404: Integration deleted (soft delete)
    if integration.deleted_at is not None:
        logger.warning(
            "webhook_integration_deleted",
            webhook_path=webhook_path,
            integration_id=integration.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Webhook not found"},
        )

    # 404: Integration not active
    if integration.status != IntegrationStatus.active:
        logger.warning(
            "webhook_integration_inactive",
            webhook_path=webhook_path,
            integration_id=integration.id,
            status=integration.status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Webhook not found"},
        )

    # 404: Inbound config not active
    if not inbound_config.is_active:
        logger.warning(
            "webhook_config_inactive",
            webhook_path=webhook_path,
            integration_id=integration.id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Webhook not found"},
        )

    # Validate authentication based on auth_method
    auth_method = inbound_config.auth_method
    auth_success = False

    if auth_method == InboundAuthMethod.none:
        # No authentication required
        auth_success = True
        logger.debug(
            "webhook_auth_none",
            webhook_path=webhook_path,
            integration_id=integration.id,
        )

    elif auth_method == InboundAuthMethod.api_key:
        auth_success = _verify_api_key_auth(inbound_config, x_api_key)
        logger.debug(
            "webhook_auth_api_key",
            webhook_path=webhook_path,
            integration_id=integration.id,
            success=auth_success,
        )

    elif auth_method == InboundAuthMethod.signature:
        auth_success = _verify_signature_auth(
            inbound_config, body, x_signature, x_hub_signature_256
        )
        logger.debug(
            "webhook_auth_signature",
            webhook_path=webhook_path,
            integration_id=integration.id,
            success=auth_success,
        )

    elif auth_method == InboundAuthMethod.bearer:
        auth_success = _verify_bearer_auth(inbound_config, authorization)
        logger.debug(
            "webhook_auth_bearer",
            webhook_path=webhook_path,
            integration_id=integration.id,
            success=auth_success,
        )

    elif auth_method == InboundAuthMethod.ed25519:
        # Ed25519 verification (Discord interactions)
        if not x_signature_ed25519 or not x_signature_timestamp:
            auth_success = False
        elif not inbound_config.signature_secret:
            auth_success = False
        else:
            try:
                public_key_hex = encryption_service.decrypt(inbound_config.signature_secret)
                auth_success = discord_interaction_service.verify_signature(
                    public_key_hex=public_key_hex,
                    signature_hex=x_signature_ed25519,
                    timestamp=x_signature_timestamp,
                    body=body,
                )
            except Exception:
                auth_success = False
        logger.debug(
            "webhook_auth_ed25519",
            webhook_path=webhook_path,
            integration_id=integration.id,
            success=auth_success,
        )

    # 401: Authentication failed
    if not auth_success:
        logger.warning(
            "webhook_auth_failed",
            webhook_path=webhook_path,
            integration_id=integration.id,
            auth_method=auth_method.value,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "AuthenticationFailed", "message": "Authentication failed"},
        )

    # Discord PING/Interaction short-circuit for Ed25519-authenticated integrations
    is_discord_interaction = False
    if auth_method == InboundAuthMethod.ed25519:
        try:
            ping_payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            ping_payload = {}
        if discord_interaction_service.is_ping(ping_payload):
            logger.info(
                "discord_ping_pong",
                webhook_path=webhook_path,
                integration_id=integration.id,
            )
            return JSONResponse(content=discord_interaction_service.pong_response())
        if discord_interaction_service.is_interaction(ping_payload):
            is_discord_interaction = True
            logger.info(
                "discord_interaction_deferred",
                webhook_path=webhook_path,
                integration_id=integration.id,
                interaction_type=ping_payload.get("type"),
            )

    # Parse body as JSON for transformation (INT-011)
    try:
        raw_payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        # If body is not valid JSON, wrap it as a raw string
        raw_payload = {"raw": body.decode("utf-8", errors="replace") if body else ""}

    # Apply payload transformation (INT-011)
    transformed = _transform_payload(
        inbound_config=inbound_config,
        raw_payload=raw_payload,
        provider=integration.provider.value,
    )

    # =========================================================================
    # INT-012: Event Routing - Log event and trigger async routing
    # =========================================================================

    # Create webhook event record
    webhook_event = IntegrationWebhookEvent(
        id=str(uuid.uuid4()),
        integration_id=integration.id,
        organization_id=integration.organization_id,
        webhook_path=webhook_path,
        provider=integration.provider.value,
        event_type=transformed.event_type,
        raw_payload=raw_payload,
        transformed_payload={
            "event_type": transformed.event_type,
            "timestamp": transformed.timestamp,
            "source": transformed.source,
            "provider": transformed.provider,
            "data": transformed.data,
        },
        destination_service=inbound_config.destination_service.value,
        destination_config=inbound_config.destination_config,
        status=IntegrationWebhookEventStatus.received,
    )
    db.add(webhook_event)
    db.commit()
    db.refresh(webhook_event)

    # Create delivery record
    webhook_delivery = IntegrationWebhookDelivery(
        id=str(uuid.uuid4()),
        event_id=webhook_event.id,
        destination_service=inbound_config.destination_service.value,
        status="pending",
    )
    db.add(webhook_delivery)
    db.commit()
    db.refresh(webhook_delivery)

    # Trigger async routing via Celery
    route_integration_event = get_route_integration_event_task()
    celery_task = route_integration_event.delay(
        event_id=webhook_event.id,
        delivery_id=webhook_delivery.id,
        destination_service=inbound_config.destination_service.value,
        destination_config=inbound_config.destination_config or {},
        transformed_payload=webhook_event.transformed_payload,
        integration_id=integration.id,
        organization_id=integration.organization_id,
    )

    # Update delivery with Celery task ID
    webhook_delivery.celery_task_id = celery_task.id
    db.commit()

    logger.info(
        "webhook_received_routing_triggered",
        webhook_path=webhook_path,
        integration_id=integration.id,
        provider=integration.provider.value,
        auth_method=auth_method.value,
        body_size=len(body),
        event_type=transformed.event_type,
        webhook_event_id=webhook_event.id,
        delivery_id=webhook_delivery.id,
        celery_task_id=celery_task.id,
        destination_service=inbound_config.destination_service.value,
    )

    # Discord interactions: return deferred response (type 5) so Discord shows "thinking..."
    # The actual response will be sent via follow-up webhook within 15 minutes
    if is_discord_interaction:
        return JSONResponse(content=discord_interaction_service.deferred_response())

    return WebhookResponse(
        received=True,
        webhook_path=webhook_path,
        integration_id=integration.id,
        provider=integration.provider.value,
        message="Webhook received and routing triggered",
        # Transformed payload fields (INT-011)
        event_type=transformed.event_type,
        timestamp=transformed.timestamp,
        source=transformed.source,
        data=transformed.data,
    )


# =============================================================================
# Discord Follow-up Endpoint
# =============================================================================


class FollowupRequest(BaseModel):
    """Request to send a follow-up response to a Discord interaction."""
    interaction_token: str = Field(..., description="Discord interaction token (from original event)")
    application_id: str = Field(..., description="Discord application/bot ID")
    content: str = Field(..., description="Message content to send")
    embeds: Optional[List[dict]] = Field(None, description="Optional Discord embed objects")


@router.post(
    "/integrations/{integration_id}/followup",
    summary="Send Discord interaction follow-up",
    description="""
    Send a follow-up message to a deferred Discord interaction.

    After returning a deferred response (type 5) to Discord, this endpoint
    sends the actual response within the 15-minute interaction token window.

    No bot token is needed — the interaction token acts as a temporary webhook.
    """,
)
async def send_interaction_followup(
    integration_id: str,
    request: FollowupRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("integrations", "execute")),
):
    """Send a follow-up response to a Discord interaction."""
    # Verify the integration exists and belongs to the caller's org
    integration = (
        db.query(Integration)
        .filter(
            Integration.id == integration_id,
            Integration.organization_id == auth.organization_id,
            Integration.deleted_at.is_(None),
        )
        .first()
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    from src.services.discord_rest_service import DiscordRestService
    discord_rest = DiscordRestService()

    try:
        result = await discord_rest.send_followup(
            application_id=request.application_id,
            interaction_token=request.interaction_token,
            content=request.content,
            embeds=request.embeds,
        )
        logger.info(
            "discord_followup_sent",
            integration_id=integration_id,
            application_id=request.application_id,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(
            "discord_followup_failed",
            integration_id=integration_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send follow-up to Discord: {str(e)}",
        )


# =============================================================================
# Action Execution Endpoint (INT-013)
# =============================================================================


class ActionExecuteRequest(BaseModel):
    """Request schema for executing an outbound action."""

    # Action-specific parameters - merged with default_template
    content: Optional[str] = Field(None, description="Message content for send_message/send_blocks")
    title: Optional[str] = Field(None, description="Title for embeds/issues")
    description: Optional[str] = Field(None, description="Description for embeds/issues")
    color: Optional[Any] = Field(None, description="Color for Discord embeds (int, #hex, or 0xhex)")
    fields: Optional[List[dict]] = Field(None, description="Fields for Discord embeds")
    blocks: Optional[List[dict]] = Field(None, description="Slack Block Kit blocks")
    body: Optional[str] = Field(None, description="Body text for GitHub issues/comments")
    repo: Optional[str] = Field(None, description="GitHub repository (owner/repo)")
    issue_number: Optional[int] = Field(None, description="GitHub issue number for comments")
    labels: Optional[List[str]] = Field(None, description="Labels for GitHub issues")
    url: Optional[str] = Field(None, description="Target URL for generic webhook actions")
    headers: Optional[dict] = Field(None, description="Custom headers for webhook actions")
    payload: Optional[dict] = Field(None, description="Custom payload for generic POST/PUT")
    channel_id: Optional[str] = Field(None, description="Channel ID for Slack/Discord")

    # Discord-specific options (INT-014)
    username: Optional[str] = Field(None, description="Override bot username for Discord/Slack webhooks")
    avatar_url: Optional[str] = Field(None, description="Override bot avatar URL for Discord webhooks")
    thread_id: Optional[str] = Field(None, description="Discord forum thread ID to post to")
    timestamp: Optional[str] = Field(None, description="ISO8601 timestamp for Discord embeds")
    footer_text: Optional[str] = Field(None, description="Footer text for Discord embeds")
    footer_icon_url: Optional[str] = Field(None, description="Footer icon URL for Discord embeds")
    author_name: Optional[str] = Field(None, description="Author name for Discord embeds")
    author_url: Optional[str] = Field(None, description="Author URL for Discord embeds")
    author_icon_url: Optional[str] = Field(None, description="Author icon URL for Discord embeds")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL for Discord embeds")
    image_url: Optional[str] = Field(None, description="Image URL for Discord embeds")

    # Slack-specific options (INT-015)
    channel: Optional[str] = Field(None, description="Slack channel override (for bot tokens)")
    icon_emoji: Optional[str] = Field(None, description="Emoji for Slack bot icon (e.g., :robot_face:)")
    icon_url: Optional[str] = Field(None, description="URL for Slack bot icon image")
    thread_ts: Optional[str] = Field(None, description="Slack thread timestamp to reply to")
    unfurl_links: Optional[bool] = Field(None, description="Enable link unfurling in Slack")
    unfurl_media: Optional[bool] = Field(None, description="Enable media unfurling in Slack")
    mrkdwn: Optional[bool] = Field(None, description="Enable mrkdwn formatting in Slack")

    # Execution options
    async_execution: bool = Field(
        default=False,
        description="Execute asynchronously via Celery and return job ID"
    )


class ActionExecuteResponse(BaseModel):
    """Response schema for successful action execution."""

    success: bool
    integration_id: str
    action_type: str
    # For sync execution: actual result from provider
    result: Optional[dict] = None
    # For async execution: job ID to track
    job_id: Optional[str] = None
    message: str


class ActionRateLimitResponse(BaseModel):
    """Response schema for rate limit exceeded."""

    error: str = "RateLimitExceeded"
    message: str
    retry_after_seconds: int


def get_execute_integration_action_task():
    """Lazy import of Celery task to avoid import issues during testing."""
    from src.core.tasks import execute_integration_action
    return execute_integration_action


def _check_rate_limit(
    integration_id: str,
    outbound_config: IntegrationOutboundConfig,
) -> tuple[bool, int]:
    """
    Check if rate limit is exceeded for an integration's outbound actions.

    Returns:
        tuple: (is_allowed: bool, retry_after_seconds: int)
    """
    if not outbound_config.rate_limit_requests or not outbound_config.rate_limit_window_seconds:
        # No rate limit configured
        return True, 0

    from src.config import settings

    try:
        r = redis.from_url(settings.REDIS_URL)
        rate_limit_key = f"rate_limit:integration:{integration_id}:actions"

        # Get current count
        current_count = r.get(rate_limit_key)
        if current_count is None:
            # First request in this window
            r.setex(
                rate_limit_key,
                outbound_config.rate_limit_window_seconds,
                1
            )
            return True, 0

        current_count = int(current_count)
        if current_count >= outbound_config.rate_limit_requests:
            # Rate limit exceeded
            ttl = r.ttl(rate_limit_key)
            return False, ttl if ttl > 0 else outbound_config.rate_limit_window_seconds

        # Increment counter
        r.incr(rate_limit_key)
        return True, 0

    except Exception as e:
        # If Redis fails, log but allow the request (fail open for availability)
        logger.warning(
            "rate_limit_check_failed",
            integration_id=integration_id,
            error=str(e),
        )
        return True, 0


def _merge_action_params(
    request_params: dict,
    default_template: Optional[dict],
) -> dict:
    """
    Merge request parameters with default template.

    Request params take precedence over defaults.
    """
    if not default_template:
        return request_params

    # Start with defaults, then override with request params
    merged = {**default_template}
    for key, value in request_params.items():
        if value is not None:
            merged[key] = value

    return merged


@router.post(
    "/integrations/{integration_id}/actions/{action_type}",
    response_model=ActionExecuteResponse,
    responses={
        200: {"description": "Action executed successfully"},
        400: {"description": "Invalid action type or parameters"},
        404: {"description": "Integration or outbound config not found"},
        429: {"description": "Rate limit exceeded", "model": ActionRateLimitResponse},
    },
    summary="Execute outbound action",
    description="""
    Execute an outbound action for an integration.

    **Request Body Parameters:**
    Parameters depend on the action_type and provider. Request parameters are merged
    with the default_template from the outbound config, with request params taking precedence.

    **Discord Actions:**
    - send_message: content (required)
    - send_embed: title, description, color, fields

    **Slack Actions:**
    - send_message: content (required), channel_id
    - send_blocks: blocks (required), channel_id

    **GitHub Actions:**
    - create_issue: title, body, repo, labels
    - post_comment: body, repo, issue_number

    **Generic Webhook Actions:**
    - post/put: url, payload, headers

    **Execution Modes:**
    - Synchronous (default): Returns the action result directly
    - Asynchronous (async_execution=true): Returns a job_id for tracking

    **Rate Limiting:**
    If rate_limit_requests and rate_limit_window_seconds are configured on the
    outbound config, requests exceeding the limit will receive a 429 response
    with retry_after_seconds.
    """,
)
async def execute_action(
    integration_id: str,
    action_type: str,
    data: ActionExecuteRequest,
    auth: Annotated[AuthContext, Depends(require_permission("integrations", "update"))],
    db: Session = Depends(get_db),
):
    """
    Execute an outbound action for an integration.

    INT-013: Action execution endpoint with rate limiting and default template merging.
    """
    # Get integration with outbound config
    integration = _get_integration_or_404(
        db, integration_id, auth.organization_id, load_relations=True
    )

    # Check if outbound config exists
    if not integration.outbound_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outbound config not found for integration {integration_id}. "
                   "Configure outbound actions first with PUT /integrations/{id}/outbound",
        )

    outbound_config = integration.outbound_config

    # Check if outbound config is active
    if not outbound_config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outbound config is not active",
        )

    # Validate action_type matches the configured action_type
    try:
        requested_action_type = OutboundActionType(action_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action_type: {action_type}. "
                   f"Valid types: {', '.join([t.value for t in OutboundActionType])}",
        )

    if outbound_config.action_type != requested_action_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action type '{action_type}' does not match configured action type "
                   f"'{outbound_config.action_type.value}' for this integration",
        )

    # Check rate limit
    is_allowed, retry_after = _check_rate_limit(integration_id, outbound_config)
    if not is_allowed:
        logger.warning(
            "action_rate_limit_exceeded",
            integration_id=integration_id,
            action_type=action_type,
            retry_after=retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RateLimitExceeded",
                "message": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                "retry_after_seconds": retry_after,
            },
        )

    # Merge request params with default template
    request_params = data.model_dump(exclude_none=True, exclude={"async_execution"})
    merged_params = _merge_action_params(request_params, outbound_config.default_template)

    logger.info(
        "executing_action",
        integration_id=integration_id,
        action_type=action_type,
        provider=integration.provider.value,
        async_execution=data.async_execution,
    )

    # Get the appropriate credential for this action
    # For webhook-based providers (Discord, Slack), we need the webhook_url
    # For API-based providers (GitHub), we need the api_key or oauth_token
    # For custom_webhook, we also extract credential_metadata for custom headers (INT-016)
    webhook_url = None
    api_token = None
    credential_metadata = None

    for cred in integration.credentials:
        if cred.credential_type == CredentialType.webhook_url:
            webhook_url = encryption_service.decrypt(cred.encrypted_value)
            credential_metadata = cred.credential_metadata  # For custom_webhook headers (INT-016)
        elif cred.credential_type in [CredentialType.api_key, CredentialType.oauth_token, CredentialType.bot_token]:
            # Skip refresh tokens - only use access tokens for API calls
            meta = cred.credential_metadata or {}
            if meta.get("token_subtype") == "refresh_token" or meta.get("token_type") == "refresh":
                continue
            api_token = encryption_service.decrypt(cred.encrypted_value)

    # Execute synchronously or asynchronously
    if data.async_execution:
        # Queue for async execution
        execute_task = get_execute_integration_action_task()
        celery_task = execute_task.delay(
            integration_id=integration_id,
            organization_id=auth.organization_id,
            action_type=action_type,
            provider=integration.provider.value,
            merged_params=merged_params,
            webhook_url=webhook_url,
            api_token=api_token,
            credential_metadata=credential_metadata,  # INT-016: Pass metadata for custom headers
        )

        logger.info(
            "action_queued",
            integration_id=integration_id,
            action_type=action_type,
            job_id=celery_task.id,
        )

        return ActionExecuteResponse(
            success=True,
            integration_id=integration_id,
            action_type=action_type,
            job_id=celery_task.id,
            message="Action queued for async execution",
        )
    else:
        # Execute synchronously
        try:
            result = await _execute_action_sync(
                provider=integration.provider.value,
                action_type=action_type,
                params=merged_params,
                webhook_url=webhook_url,
                api_token=api_token,
                credential_metadata=credential_metadata,  # INT-016: Pass metadata for custom headers
            )

            logger.info(
                "action_executed_sync",
                integration_id=integration_id,
                action_type=action_type,
                success=True,
            )

            return ActionExecuteResponse(
                success=True,
                integration_id=integration_id,
                action_type=action_type,
                result=result,
                message="Action executed successfully",
            )

        except Exception as e:
            logger.error(
                "action_execution_failed",
                integration_id=integration_id,
                action_type=action_type,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Action execution failed: {str(e)}",
            )


# =============================================================================
# Discord Action Helpers (INT-014)
# =============================================================================


def _validate_discord_content(content: str) -> None:
    """Validate Discord message content against character limits."""
    if len(content) > DISCORD_LIMITS["content"]:
        raise ValueError(
            f"Message content exceeds Discord limit of {DISCORD_LIMITS['content']} characters "
            f"(got {len(content)})"
        )


def _validate_discord_embed(embed: dict) -> None:
    """
    Validate Discord embed against character limits.

    Discord embed limits:
    - title: 256 characters
    - description: 4096 characters
    - field.name: 256 characters
    - field.value: 1024 characters
    - fields: max 25
    - footer.text: 2048 characters
    - author.name: 256 characters
    - total: 6000 characters
    """
    total_chars = 0

    # Validate title
    title = embed.get("title", "")
    if len(title) > DISCORD_LIMITS["embed_title"]:
        raise ValueError(
            f"Embed title exceeds Discord limit of {DISCORD_LIMITS['embed_title']} characters "
            f"(got {len(title)})"
        )
    total_chars += len(title)

    # Validate description
    description = embed.get("description", "")
    if len(description) > DISCORD_LIMITS["embed_description"]:
        raise ValueError(
            f"Embed description exceeds Discord limit of {DISCORD_LIMITS['embed_description']} characters "
            f"(got {len(description)})"
        )
    total_chars += len(description)

    # Validate footer
    footer = embed.get("footer", {})
    if isinstance(footer, dict):
        footer_text = footer.get("text", "")
        if len(footer_text) > DISCORD_LIMITS["embed_footer_text"]:
            raise ValueError(
                f"Embed footer text exceeds Discord limit of {DISCORD_LIMITS['embed_footer_text']} characters "
                f"(got {len(footer_text)})"
            )
        total_chars += len(footer_text)

    # Validate author
    author = embed.get("author", {})
    if isinstance(author, dict):
        author_name = author.get("name", "")
        if len(author_name) > DISCORD_LIMITS["embed_author_name"]:
            raise ValueError(
                f"Embed author name exceeds Discord limit of {DISCORD_LIMITS['embed_author_name']} characters "
                f"(got {len(author_name)})"
            )
        total_chars += len(author_name)

    # Validate fields
    fields = embed.get("fields", [])
    if len(fields) > DISCORD_LIMITS["embed_fields_max"]:
        raise ValueError(
            f"Embed exceeds Discord limit of {DISCORD_LIMITS['embed_fields_max']} fields "
            f"(got {len(fields)})"
        )

    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise ValueError(f"Embed field {i} must be a dictionary")

        field_name = field.get("name", "")
        if not field_name:
            raise ValueError(f"Embed field {i} requires a 'name'")
        if len(field_name) > DISCORD_LIMITS["embed_field_name"]:
            raise ValueError(
                f"Embed field {i} name exceeds Discord limit of {DISCORD_LIMITS['embed_field_name']} characters "
                f"(got {len(field_name)})"
            )
        total_chars += len(field_name)

        field_value = field.get("value", "")
        if not field_value:
            raise ValueError(f"Embed field {i} requires a 'value'")
        if len(field_value) > DISCORD_LIMITS["embed_field_value"]:
            raise ValueError(
                f"Embed field {i} value exceeds Discord limit of {DISCORD_LIMITS['embed_field_value']} characters "
                f"(got {len(field_value)})"
            )
        total_chars += len(field_value)

    # Validate total embed size
    if total_chars > DISCORD_LIMITS["embed_total"]:
        raise ValueError(
            f"Total embed content exceeds Discord limit of {DISCORD_LIMITS['embed_total']} characters "
            f"(got {total_chars})"
        )


async def _execute_discord_action(
    webhook_url: Optional[str],
    action_type: str,
    params: dict,
) -> dict:
    """
    Execute Discord-specific outbound actions (INT-014).

    Actions:
    - send_message: Plain text via webhook
    - send_embed: Rich embed with title, description, color, fields

    Uses webhook_url credential, validates Discord character limits,
    returns Discord message ID on success.
    """
    import httpx

    if not webhook_url:
        raise ValueError("Discord actions require a webhook_url credential")

    # Add ?wait=true to get message ID in response
    if "?" in webhook_url:
        request_url = f"{webhook_url}&wait=true"
    else:
        request_url = f"{webhook_url}?wait=true"

    if action_type == "send_message":
        content = params.get("content")
        if not content:
            raise ValueError("send_message requires 'content' parameter")

        # Validate character limits
        _validate_discord_content(content)

        # Build payload
        payload: dict[str, Any] = {"content": content}

        # Optional: username override
        if params.get("username"):
            payload["username"] = params["username"]

        # Optional: avatar URL override
        if params.get("avatar_url"):
            payload["avatar_url"] = params["avatar_url"]

        # Optional: thread_id for posting to a forum thread
        if params.get("thread_id"):
            if "?" in request_url:
                request_url = f"{request_url}&thread_id={params['thread_id']}"
            else:
                request_url = f"{request_url}?thread_id={params['thread_id']}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                request_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()

            # Parse response to get message ID
            try:
                response_data = response.json()
                message_id = response_data.get("id")
                return {
                    "status": "sent",
                    "status_code": response.status_code,
                    "message_id": message_id,
                    "channel_id": response_data.get("channel_id"),
                }
            except Exception:
                # Fallback if response is not JSON
                return {"status": "sent", "status_code": response.status_code}

    elif action_type == "send_embed":
        # Build embed object
        embed: dict[str, Any] = {}

        # Required fields (at least one of title or description)
        if params.get("title"):
            embed["title"] = params["title"]
        if params.get("description"):
            embed["description"] = params["description"]

        if not embed:
            raise ValueError("send_embed requires at least 'title' or 'description' parameter")

        # Optional: URL (title becomes hyperlink)
        if params.get("url"):
            embed["url"] = params["url"]

        # Optional: Color (decimal or hex)
        if params.get("color") is not None:
            color = params["color"]
            # Convert hex string to int if needed
            if isinstance(color, str):
                if color.startswith("#"):
                    color = int(color[1:], 16)
                elif color.startswith("0x"):
                    color = int(color, 16)
                else:
                    color = int(color)
            embed["color"] = color

        # Optional: Timestamp (ISO8601 format)
        if params.get("timestamp"):
            embed["timestamp"] = params["timestamp"]

        # Optional: Footer
        if params.get("footer_text"):
            embed["footer"] = {
                "text": params["footer_text"],
            }
            if params.get("footer_icon_url"):
                embed["footer"]["icon_url"] = params["footer_icon_url"]

        # Optional: Author
        if params.get("author_name"):
            embed["author"] = {
                "name": params["author_name"],
            }
            if params.get("author_url"):
                embed["author"]["url"] = params["author_url"]
            if params.get("author_icon_url"):
                embed["author"]["icon_url"] = params["author_icon_url"]

        # Optional: Thumbnail
        if params.get("thumbnail_url"):
            embed["thumbnail"] = {"url": params["thumbnail_url"]}

        # Optional: Image
        if params.get("image_url"):
            embed["image"] = {"url": params["image_url"]}

        # Optional: Fields (array of {name, value, inline?})
        if params.get("fields"):
            fields = params["fields"]
            if not isinstance(fields, list):
                raise ValueError("'fields' must be a list of field objects")
            # Normalize fields to ensure proper structure
            normalized_fields = []
            for field in fields:
                if not isinstance(field, dict):
                    raise ValueError("Each field must be a dictionary with 'name' and 'value'")
                normalized_field = {
                    "name": field.get("name", ""),
                    "value": field.get("value", ""),
                }
                if "inline" in field:
                    normalized_field["inline"] = bool(field["inline"])
                normalized_fields.append(normalized_field)
            embed["fields"] = normalized_fields

        # Validate embed limits
        _validate_discord_embed(embed)

        # Build payload
        payload = {"embeds": [embed]}

        # Optional: Content alongside embed
        if params.get("content"):
            _validate_discord_content(params["content"])
            payload["content"] = params["content"]

        # Optional: username override
        if params.get("username"):
            payload["username"] = params["username"]

        # Optional: avatar URL override
        if params.get("avatar_url"):
            payload["avatar_url"] = params["avatar_url"]

        # Optional: thread_id for posting to a forum thread
        if params.get("thread_id"):
            if "?" in request_url:
                request_url = f"{request_url}&thread_id={params['thread_id']}"
            else:
                request_url = f"{request_url}?thread_id={params['thread_id']}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                request_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()

            # Parse response to get message ID
            try:
                response_data = response.json()
                message_id = response_data.get("id")
                return {
                    "status": "sent",
                    "status_code": response.status_code,
                    "message_id": message_id,
                    "channel_id": response_data.get("channel_id"),
                }
            except Exception:
                # Fallback if response is not JSON
                return {"status": "sent", "status_code": response.status_code}

    else:
        raise ValueError(f"Unsupported Discord action type: {action_type}")


# =============================================================================
# Slack Action Helpers (INT-015)
# =============================================================================


def _validate_slack_text(text: str, limit_key: str = "text") -> None:
    """Validate Slack text against character limits."""
    limit = SLACK_LIMITS[limit_key]
    if len(text) > limit:
        raise ValueError(
            f"Text exceeds Slack limit of {limit} characters "
            f"(got {len(text)})"
        )


def _validate_slack_blocks(blocks: list) -> None:
    """
    Validate Slack Block Kit blocks against limits.

    Slack Block Kit limits:
    - Max 50 blocks per message
    - Section text: 3000 characters
    - Section fields: max 10
    - Header text: 150 characters
    - Image alt_text: 2000 characters
    - Context elements: max 10
    - Actions elements: max 25
    - Button text: 75 characters
    """
    if not isinstance(blocks, list):
        raise ValueError("'blocks' must be a list")

    if len(blocks) > SLACK_LIMITS["blocks_max"]:
        raise ValueError(
            f"Message exceeds Slack limit of {SLACK_LIMITS['blocks_max']} blocks "
            f"(got {len(blocks)})"
        )

    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError(f"Block {i} must be a dictionary")

        block_type = block.get("type")
        if not block_type:
            raise ValueError(f"Block {i} requires a 'type' field")

        # Validate block_id if present
        block_id = block.get("block_id", "")
        if len(block_id) > SLACK_LIMITS["block_id"]:
            raise ValueError(
                f"Block {i} block_id exceeds Slack limit of {SLACK_LIMITS['block_id']} characters "
                f"(got {len(block_id)})"
            )

        # Validate based on block type
        if block_type == "section":
            _validate_section_block(block, i)
        elif block_type == "header":
            _validate_header_block(block, i)
        elif block_type == "image":
            _validate_image_block(block, i)
        elif block_type == "context":
            _validate_context_block(block, i)
        elif block_type == "actions":
            _validate_actions_block(block, i)
        elif block_type == "divider":
            # Divider has no content to validate
            pass
        elif block_type == "input":
            _validate_input_block(block, i)
        # Other block types (file, rich_text, video) have fewer strict limits


def _validate_section_block(block: dict, index: int) -> None:
    """Validate a Slack section block."""
    text = block.get("text")
    if text:
        if isinstance(text, dict):
            text_content = text.get("text", "")
        else:
            text_content = str(text)
        if len(text_content) > SLACK_LIMITS["section_text"]:
            raise ValueError(
                f"Block {index} section text exceeds Slack limit of {SLACK_LIMITS['section_text']} characters "
                f"(got {len(text_content)})"
            )

    fields = block.get("fields", [])
    if len(fields) > SLACK_LIMITS["section_fields_max"]:
        raise ValueError(
            f"Block {index} section exceeds Slack limit of {SLACK_LIMITS['section_fields_max']} fields "
            f"(got {len(fields)})"
        )
    for j, field in enumerate(fields):
        if isinstance(field, dict):
            field_text = field.get("text", "")
        else:
            field_text = str(field)
        if len(field_text) > SLACK_LIMITS["section_field_text"]:
            raise ValueError(
                f"Block {index} field {j} text exceeds Slack limit of {SLACK_LIMITS['section_field_text']} characters "
                f"(got {len(field_text)})"
            )


def _validate_header_block(block: dict, index: int) -> None:
    """Validate a Slack header block."""
    text = block.get("text")
    if not text:
        raise ValueError(f"Block {index} header requires a 'text' field")
    if isinstance(text, dict):
        text_content = text.get("text", "")
    else:
        text_content = str(text)
    if len(text_content) > SLACK_LIMITS["header_text"]:
        raise ValueError(
            f"Block {index} header text exceeds Slack limit of {SLACK_LIMITS['header_text']} characters "
            f"(got {len(text_content)})"
        )


def _validate_image_block(block: dict, index: int) -> None:
    """Validate a Slack image block."""
    alt_text = block.get("alt_text", "")
    if len(alt_text) > SLACK_LIMITS["image_alt_text"]:
        raise ValueError(
            f"Block {index} image alt_text exceeds Slack limit of {SLACK_LIMITS['image_alt_text']} characters "
            f"(got {len(alt_text)})"
        )
    title = block.get("title")
    if title:
        if isinstance(title, dict):
            title_text = title.get("text", "")
        else:
            title_text = str(title)
        if len(title_text) > SLACK_LIMITS["image_title"]:
            raise ValueError(
                f"Block {index} image title exceeds Slack limit of {SLACK_LIMITS['image_title']} characters "
                f"(got {len(title_text)})"
            )


def _validate_context_block(block: dict, index: int) -> None:
    """Validate a Slack context block."""
    elements = block.get("elements", [])
    if len(elements) > SLACK_LIMITS["context_elements_max"]:
        raise ValueError(
            f"Block {index} context exceeds Slack limit of {SLACK_LIMITS['context_elements_max']} elements "
            f"(got {len(elements)})"
        )


def _validate_actions_block(block: dict, index: int) -> None:
    """Validate a Slack actions block."""
    elements = block.get("elements", [])
    if len(elements) > SLACK_LIMITS["actions_elements_max"]:
        raise ValueError(
            f"Block {index} actions exceeds Slack limit of {SLACK_LIMITS['actions_elements_max']} elements "
            f"(got {len(elements)})"
        )

    # Validate button elements
    for j, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        elem_type = element.get("type")
        if elem_type == "button":
            text = element.get("text")
            if text:
                if isinstance(text, dict):
                    text_content = text.get("text", "")
                else:
                    text_content = str(text)
                if len(text_content) > SLACK_LIMITS["button_text"]:
                    raise ValueError(
                        f"Block {index} element {j} button text exceeds Slack limit of "
                        f"{SLACK_LIMITS['button_text']} characters (got {len(text_content)})"
                    )
            value = element.get("value", "")
            if len(value) > SLACK_LIMITS["button_value"]:
                raise ValueError(
                    f"Block {index} element {j} button value exceeds Slack limit of "
                    f"{SLACK_LIMITS['button_value']} characters (got {len(value)})"
                )


def _validate_input_block(block: dict, index: int) -> None:
    """Validate a Slack input block."""
    label = block.get("label")
    if label:
        if isinstance(label, dict):
            label_text = label.get("text", "")
        else:
            label_text = str(label)
        if len(label_text) > SLACK_LIMITS["input_label"]:
            raise ValueError(
                f"Block {index} input label exceeds Slack limit of {SLACK_LIMITS['input_label']} characters "
                f"(got {len(label_text)})"
            )
    hint = block.get("hint")
    if hint:
        if isinstance(hint, dict):
            hint_text = hint.get("text", "")
        else:
            hint_text = str(hint)
        if len(hint_text) > SLACK_LIMITS["input_hint"]:
            raise ValueError(
                f"Block {index} input hint exceeds Slack limit of {SLACK_LIMITS['input_hint']} characters "
                f"(got {len(hint_text)})"
            )


async def _execute_slack_action(
    webhook_url: Optional[str],
    action_type: str,
    params: dict,
) -> dict:
    """
    Execute Slack-specific outbound actions (INT-015).

    Actions:
    - send_message: Plain text via webhook
    - send_blocks: Block Kit formatted message

    Uses webhook_url credential, validates Slack character limits,
    returns Slack timestamp (ts) on success.
    """
    import httpx

    if not webhook_url:
        raise ValueError("Slack actions require a webhook_url credential")

    if action_type == "send_message":
        content = params.get("content")
        if not content:
            raise ValueError("send_message requires 'content' parameter")

        # Validate character limits
        _validate_slack_text(content)

        # Build payload
        payload: dict[str, Any] = {"text": content}

        # Optional: channel override (only works with bot tokens, not webhooks)
        if params.get("channel"):
            payload["channel"] = params["channel"]

        # Optional: username override
        if params.get("username"):
            payload["username"] = params["username"]

        # Optional: icon_emoji or icon_url
        if params.get("icon_emoji"):
            payload["icon_emoji"] = params["icon_emoji"]
        elif params.get("icon_url"):
            payload["icon_url"] = params["icon_url"]

        # Optional: thread_ts for replying in a thread
        if params.get("thread_ts"):
            payload["thread_ts"] = params["thread_ts"]

        # Optional: unfurl_links and unfurl_media
        if params.get("unfurl_links") is not None:
            payload["unfurl_links"] = params["unfurl_links"]
        if params.get("unfurl_media") is not None:
            payload["unfurl_media"] = params["unfurl_media"]

        # Optional: mrkdwn formatting
        if params.get("mrkdwn") is not None:
            payload["mrkdwn"] = params["mrkdwn"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()

            # Parse response to get timestamp
            # Slack webhooks return "ok" on success, or JSON with ts for API calls
            try:
                response_text = response.text
                if response_text == "ok":
                    return {
                        "status": "sent",
                        "status_code": response.status_code,
                        "message": "ok",
                    }
                else:
                    # Try to parse as JSON (for Slack API responses)
                    response_data = response.json()
                    return {
                        "status": "sent",
                        "status_code": response.status_code,
                        "ts": response_data.get("ts"),
                        "channel": response_data.get("channel"),
                    }
            except Exception:
                return {"status": "sent", "status_code": response.status_code, "response": response.text}

    elif action_type == "send_blocks":
        blocks = params.get("blocks")
        if not blocks:
            raise ValueError("send_blocks requires 'blocks' parameter")

        # Validate blocks
        _validate_slack_blocks(blocks)

        # Build payload
        payload = {"blocks": blocks}

        # Fallback text is required for notifications and accessibility
        if params.get("content"):
            _validate_slack_text(params["content"])
            payload["text"] = params["content"]

        # Optional: channel override
        if params.get("channel"):
            payload["channel"] = params["channel"]

        # Optional: username override
        if params.get("username"):
            payload["username"] = params["username"]

        # Optional: icon_emoji or icon_url
        if params.get("icon_emoji"):
            payload["icon_emoji"] = params["icon_emoji"]
        elif params.get("icon_url"):
            payload["icon_url"] = params["icon_url"]

        # Optional: thread_ts for replying in a thread
        if params.get("thread_ts"):
            payload["thread_ts"] = params["thread_ts"]

        # Optional: unfurl_links and unfurl_media
        if params.get("unfurl_links") is not None:
            payload["unfurl_links"] = params["unfurl_links"]
        if params.get("unfurl_media") is not None:
            payload["unfurl_media"] = params["unfurl_media"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()

            # Parse response
            try:
                response_text = response.text
                if response_text == "ok":
                    return {
                        "status": "sent",
                        "status_code": response.status_code,
                        "message": "ok",
                    }
                else:
                    # Try to parse as JSON (for Slack API responses)
                    response_data = response.json()
                    return {
                        "status": "sent",
                        "status_code": response.status_code,
                        "ts": response_data.get("ts"),
                        "channel": response_data.get("channel"),
                    }
            except Exception:
                return {"status": "sent", "status_code": response.status_code, "response": response.text}

    else:
        raise ValueError(f"Unsupported Slack action type: {action_type}")


async def _execute_action_sync(
    provider: str,
    action_type: str,
    params: dict,
    webhook_url: Optional[str] = None,
    api_token: Optional[str] = None,
    credential_metadata: Optional[dict] = None,
) -> dict:
    """
    Execute an action synchronously.

    Routes to provider-specific implementation based on provider and action_type.

    INT-016: For custom_webhook provider, credential_metadata can contain custom headers
    that are merged with headers from params (params headers take precedence).
    """
    import httpx

    # Discord actions (INT-014)
    if provider == "discord":
        return await _execute_discord_action(webhook_url, action_type, params)

    # Slack actions (INT-015)
    elif provider == "slack":
        return await _execute_slack_action(webhook_url, action_type, params)

    # GitHub actions (INT-014 will fully implement)
    elif provider == "github":
        if not api_token:
            raise ValueError("GitHub actions require an api_key or oauth_token credential")

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        if action_type == "create_issue":
            repo = params.get("repo")
            title = params.get("title")
            if not repo or not title:
                raise ValueError("create_issue requires 'repo' and 'title' parameters")

            issue_payload = {"title": title}
            if params.get("body"):
                issue_payload["body"] = params["body"]
            if params.get("labels"):
                issue_payload["labels"] = params["labels"]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.github.com/repos/{repo}/issues",
                    json=issue_payload,
                    headers=headers,
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.json()

        elif action_type == "post_comment":
            repo = params.get("repo")
            issue_number = params.get("issue_number")
            body = params.get("body")
            if not repo or not issue_number or not body:
                raise ValueError("post_comment requires 'repo', 'issue_number', and 'body' parameters")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
                    json={"body": body},
                    headers=headers,
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.json()

    # Twitter/X actions
    elif provider == "twitter":
        if not api_token:
            raise ValueError("Twitter actions require an oauth_token credential. Connect via OAuth first.")

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        if action_type == "send_message":
            content = params.get("content", "")
            if not content:
                raise ValueError("send_message requires 'content' parameter")
            if len(content) > 280:
                raise ValueError(f"Tweet exceeds 280 character limit ({len(content)} chars)")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.x.com/2/tweets",
                    json={"text": content},
                    headers=headers,
                    timeout=15.0,
                )
                response.raise_for_status()
                return response.json()
        else:
            raise ValueError(f"Unsupported action type for twitter: {action_type}")

    # Custom webhook actions (INT-016)
    elif provider == "custom_webhook":
        target_url = params.get("url") or webhook_url
        if not target_url:
            raise ValueError("Custom webhook actions require 'url' parameter or webhook_url credential")

        # INT-016: Merge headers from credential_metadata with params headers
        # Credential metadata headers are used as defaults, params headers take precedence
        custom_headers = {}
        if credential_metadata and isinstance(credential_metadata, dict):
            metadata_headers = credential_metadata.get("headers", {})
            if isinstance(metadata_headers, dict):
                custom_headers.update(metadata_headers)
        # Params headers override credential metadata headers
        params_headers = params.get("headers", {})
        if isinstance(params_headers, dict):
            custom_headers.update(params_headers)

        payload = params.get("payload", {})

        async with httpx.AsyncClient() as client:
            if action_type == "post":
                response = await client.post(
                    target_url,
                    json=payload,
                    headers=custom_headers,
                    timeout=15.0,
                )
            elif action_type == "put":
                response = await client.put(
                    target_url,
                    json=payload,
                    headers=custom_headers,
                    timeout=15.0,
                )
            elif action_type == "send_message":
                # For custom webhooks, send_message sends the content as JSON body
                content = params.get("content", "")
                response = await client.post(
                    target_url,
                    json={"content": content, "message": content},
                    headers=custom_headers,
                    timeout=15.0,
                )
            else:
                raise ValueError(f"Unsupported action type for custom_webhook: {action_type}")

            # Try to parse JSON response, fall back to text
            try:
                result = response.json()
            except Exception:
                result = {"raw_response": response.text[:1000]}

            return {
                "status_code": response.status_code,
                "response": result,
            }

    else:
        raise ValueError(f"Unsupported provider: {provider}")
