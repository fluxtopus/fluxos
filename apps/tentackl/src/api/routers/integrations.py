"""API routes for user-facing webhook integration management.

INT-018: Integrations are now managed through Mimic.
Mimic is the central integration registry and gateway.
This router proxies integration operations to the Mimic service.

Old webhook URLs (/api/events/webhook/{source_id}) are redirected
to the new Mimic gateway for backward compatibility.

Internal endpoint for receiving routed integration events from Mimic:
- POST /api/internal/integration-events
"""

# REVIEW:
# - Router is a mix of Mimic proxy endpoints, legacy redirect behavior, and internal event receiver; hard to reason about boundaries.
# - Provider defaults live in API layer (_integration_defaults), not in Mimic/service config.
# - Duplicates auth/token extraction and error mapping that could be centralized in client code.

from fastapi import APIRouter, Header, HTTPException, Depends, status, Request
from fastapi.security.utils import get_authorization_scheme_param
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import structlog

from src.api.auth_middleware import auth_middleware, AuthUser
from src.application.integrations import (
    IntegrationEventStreamUseCases,
    IntegrationUseCases,
)
from src.infrastructure.integrations import (
    MimicIntegrationAdapter,
    RedisIntegrationEventStreamAdapter,
)
from src.api.routers._integration_defaults import PROVIDER_DEFAULTS
from src.api.error_helpers import safe_error_detail
from src.clients.mimic import (
    MimicError,
    AuthenticationError as MimicAuthError,
    PermissionDeniedError as MimicPermissionError,
    ResourceNotFoundError as MimicNotFoundError,
    ServiceUnavailableError as MimicUnavailableError,
    ValidationError as MimicValidationError,
    RateLimitError as MimicRateLimitError,
    IntegrationProvider,
    IntegrationDirection,
    IntegrationStatus,
    IntegrationCreate,
    IntegrationUpdate,
    InboundConfigCreate,
    OutboundConfigCreate,
    CredentialCreate,
    CredentialType,
    InboundAuthMethod,
    DestinationService,
    OutboundActionType,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

# Singleton IntegrationUseCases (injected at startup by app.py)
integration_use_cases: Optional[IntegrationUseCases] = None
integration_event_stream_use_cases: Optional[IntegrationEventStreamUseCases] = None


def _get_integration_use_cases() -> IntegrationUseCases:
    """Get the injected use cases or fall back to creating them."""
    global integration_use_cases
    if integration_use_cases is None:
        integration_use_cases = IntegrationUseCases(
            integration_ops=MimicIntegrationAdapter()
        )
    return integration_use_cases


def _get_integration_event_stream_use_cases() -> IntegrationEventStreamUseCases:
    """Get injected stream use cases or fall back to creating them."""
    global integration_event_stream_use_cases
    if integration_event_stream_use_cases is None:
        integration_event_stream_use_cases = IntegrationEventStreamUseCases(
            event_stream_ops=RedisIntegrationEventStreamAdapter()
        )
    return integration_event_stream_use_cases


def get_bearer_token(request: Request) -> str:
    """Extract Bearer token from request headers."""
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme"
        )
    return token


def handle_mimic_error(e: Exception) -> None:
    """Convert Mimic exceptions to HTTP exceptions."""
    if isinstance(e, MimicAuthError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=safe_error_detail(str(e))
        )
    elif isinstance(e, MimicPermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e))
        )
    elif isinstance(e, MimicNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(str(e))
        )
    elif isinstance(e, MimicValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e))
        )
    elif isinstance(e, MimicRateLimitError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=safe_error_detail(str(e))
        )
    elif isinstance(e, MimicUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration service unavailable. Please try again later."
        )
    elif isinstance(e, MimicError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )
    else:
        logger.error("Unexpected error in integration operation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


# === Request/Response Models ===

class CreateIntegrationRequest(BaseModel):
    """Request to create a new integration."""
    name: str = Field(..., min_length=1, max_length=255, description="Integration name")
    provider: str = Field(..., description="Provider (discord, slack, github, stripe, custom_webhook)")
    direction: str = Field(default="bidirectional", description="Direction (inbound, outbound, bidirectional)")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (for outbound integrations)")


class UpdateIntegrationRequest(BaseModel):
    """Request to update an integration."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(None, description="Status (active, paused, error)")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (for outbound integrations)")


class IntegrationResponse(BaseModel):
    """Response model for an integration."""
    id: str
    name: str
    provider: str
    direction: str
    status: str
    webhook_url: Optional[str] = None
    inbound_config: Optional[Dict[str, Any]] = None
    outbound_config: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IntegrationListResponse(BaseModel):
    """Response model for listing integrations."""
    items: List[IntegrationResponse]
    total: int


class CredentialRequest(BaseModel):
    """Request to add a credential."""
    credential_type: str = Field(..., description="Credential type (api_key, webhook_url, oauth_token, bot_token, webhook_secret)")
    value: str = Field(..., description="Credential value (will be encrypted)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    expires_at: Optional[datetime] = Field(None, description="Expiration time for OAuth tokens")


class InboundConfigRequest(BaseModel):
    """Request to set inbound webhook configuration."""
    webhook_path: Optional[str] = Field(None, description="Custom webhook path (auto-generated if not provided)")
    auth_method: str = Field(default="api_key", description="Auth method (none, api_key, signature, ed25519, bearer)")
    signature_secret: Optional[str] = Field(None, description="Signature secret or Ed25519 public key")
    event_filters: Optional[List[str]] = Field(None, description="Event types to accept")
    transform_template: Optional[str] = Field(None, description="Jinja2 template for payload transformation")
    destination_service: str = Field(default="tentackl", description="Destination (tentackl, custom)")
    destination_config: Optional[Dict[str, Any]] = Field(None, description="Destination-specific config")


class OutboundConfigRequest(BaseModel):
    """Request to set outbound action configuration."""
    action_type: str = Field(..., description="Action type (send_message, send_embed, send_blocks, create_issue, post, put)")
    default_template: Optional[Dict[str, Any]] = Field(None, description="Default values for actions")
    rate_limit_requests: Optional[int] = Field(None, description="Max requests per window")
    rate_limit_window_seconds: Optional[int] = Field(None, description="Rate limit window in seconds")


class ExecuteActionRequest(BaseModel):
    """Request to execute an outbound action."""
    content: Optional[str] = Field(None, description="Message content")
    title: Optional[str] = Field(None, description="Embed/message title")
    description: Optional[str] = Field(None, description="Embed description")
    color: Optional[Any] = Field(None, description="Embed color")
    fields: Optional[List[Dict[str, Any]]] = Field(None, description="Embed fields")
    blocks: Optional[List[Dict[str, Any]]] = Field(None, description="Slack blocks")
    url: Optional[str] = Field(None, description="Custom webhook URL")
    payload: Optional[Dict[str, Any]] = Field(None, description="Custom payload")
    headers: Optional[Dict[str, str]] = Field(None, description="Custom headers")
    async_execution: bool = Field(default=False, description="Execute asynchronously")


# === Endpoints ===

@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    http_request: Request,
    provider: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """List all integrations for the current user's organization.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        result = await use_cases.list_integrations(
            token=token,
            provider=provider,
            direction=direction,
            status=status,
        )

        # Convert to response format, fetching detail for config status
        items = []
        for integration in result.items:
            # Try to fetch detail to include config status
            outbound_config = None
            inbound_config = None
            try:
                detail = await use_cases.get_integration(
                    integration_id=integration.id,
                    token=token,
                )
                if detail.outbound_config:
                    outbound_config = detail.outbound_config.model_dump()
                if detail.inbound_config:
                    inbound_config = detail.inbound_config.model_dump()
            except Exception:
                pass  # Non-fatal: list still works without config data

            item = IntegrationResponse(
                id=integration.id,
                name=integration.name,
                provider=integration.provider.value if hasattr(integration.provider, 'value') else integration.provider,
                direction=integration.direction.value if hasattr(integration.direction, 'value') else integration.direction,
                status=integration.status.value if hasattr(integration.status, 'value') else integration.status,
                outbound_config=outbound_config,
                inbound_config=inbound_config,
                created_at=integration.created_at,
                updated_at=integration.updated_at,
            )
            items.append(item)

        return IntegrationListResponse(
            items=items,
            total=result.total,
        )

    except MimicError as e:
        handle_mimic_error(e)


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    request: CreateIntegrationRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "create")),
):
    """Create a new integration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        # Map string values to enums
        provider = IntegrationProvider(request.provider)
        direction = IntegrationDirection(request.direction)

        # Create integration via Mimic
        result = await use_cases.create_integration(
            data=IntegrationCreate(
                name=request.name,
                provider=provider,
                direction=direction,
            ),
            token=token,
        )

        # If webhook_url provided, add it as a credential
        webhook_url = None
        if request.webhook_url:
            await use_cases.add_credential(
                integration_id=result.id,
                credential=CredentialCreate(
                    credential_type=CredentialType("webhook_url"),
                    value=request.webhook_url,
                ),
                token=token,
            )
            webhook_url = '[configured]'  # Masked for security

        # Auto-configure outbound/inbound based on provider defaults
        outbound_config = None
        inbound_config = None
        defaults = PROVIDER_DEFAULTS.get(request.provider, {})

        # Auto-configure outbound for outbound/bidirectional integrations
        if direction in (IntegrationDirection.outbound, IntegrationDirection.bidirectional):
            outbound_defaults = defaults.get("outbound")
            if outbound_defaults:
                try:
                    outbound_result = await use_cases.set_outbound_config(
                        integration_id=result.id,
                        config=OutboundConfigCreate(
                            action_type=OutboundActionType(outbound_defaults["action_type"]),
                            rate_limit_requests=outbound_defaults["rate_limit_requests"],
                            rate_limit_window_seconds=outbound_defaults["rate_limit_window_seconds"],
                        ),
                        token=token,
                    )
                    outbound_config = outbound_result
                    logger.info(
                        "Auto-configured outbound",
                        integration_id=result.id,
                        action_type=outbound_defaults["action_type"],
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to auto-configure outbound (non-fatal)",
                        integration_id=result.id,
                        error=str(e),
                    )

        # Auto-configure inbound for inbound/bidirectional integrations
        if direction in (IntegrationDirection.inbound, IntegrationDirection.bidirectional):
            inbound_defaults = defaults.get("inbound")
            if inbound_defaults:
                try:
                    inbound_result = await use_cases.set_inbound_config(
                        integration_id=result.id,
                        config=InboundConfigCreate(
                            auth_method=InboundAuthMethod(inbound_defaults["auth_method"]),
                            destination_service=DestinationService(inbound_defaults["destination_service"]),
                        ),
                        token=token,
                    )
                    inbound_config = inbound_result
                    logger.info(
                        "Auto-configured inbound",
                        integration_id=result.id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to auto-configure inbound (non-fatal)",
                        integration_id=result.id,
                        error=str(e),
                    )

        logger.info(
            "Integration created via Mimic",
            integration_id=result.id,
            name=request.name,
            user_id=user.id,
        )

        return IntegrationResponse(
            id=result.id,
            name=result.name,
            provider=result.provider.value if hasattr(result.provider, 'value') else result.provider,
            direction=result.direction.value if hasattr(result.direction, 'value') else result.direction,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            webhook_url=webhook_url,
            outbound_config=outbound_config,
            inbound_config=inbound_config,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(f"Invalid enum value: {str(e)}")
        )
    except MimicError as e:
        handle_mimic_error(e)


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """Get a specific integration by ID.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        result = await use_cases.get_integration(
            integration_id=integration_id,
            token=token,
        )

        # Build webhook URL - check inbound config first, then credentials
        webhook_url = None
        if result.inbound_config:
            webhook_url = result.inbound_config.webhook_url
        elif result.credentials:
            # For outbound integrations, look for webhook_url credential
            for cred in result.credentials:
                cred_type = cred.credential_type if isinstance(cred.credential_type, str) else cred.credential_type.value
                if cred_type == 'webhook_url':
                    # Credentials don't expose the actual value, just indicate it's configured
                    webhook_url = '[configured]'
                    break

        return IntegrationResponse(
            id=result.id,
            name=result.name,
            provider=result.provider.value if hasattr(result.provider, 'value') else result.provider,
            direction=result.direction.value if hasattr(result.direction, 'value') else result.direction,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            webhook_url=webhook_url,
            inbound_config=result.inbound_config.model_dump() if result.inbound_config else None,
            outbound_config=result.outbound_config.model_dump() if result.outbound_config else None,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    except MimicError as e:
        handle_mimic_error(e)


@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    request: UpdateIntegrationRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Update an integration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        # Build update data
        update_data = IntegrationUpdate()
        if request.name:
            update_data.name = request.name
        if request.status:
            update_data.status = IntegrationStatus(request.status)

        result = await use_cases.update_integration(
            integration_id=integration_id,
            data=update_data,
            token=token,
        )

        # Handle webhook_url by adding/updating a credential
        webhook_url = None
        if request.webhook_url:
            # Add webhook URL as a credential
            await use_cases.add_credential(
                integration_id=integration_id,
                credential=CredentialCreate(
                    credential_type=CredentialType("webhook_url"),
                    value=request.webhook_url,
                ),
                token=token,
            )
            webhook_url = '[configured]'  # Masked for security

        logger.info(
            "Integration updated via Mimic",
            integration_id=integration_id,
            user_id=user.id,
        )

        return IntegrationResponse(
            id=result.id,
            name=result.name,
            provider=result.provider.value if hasattr(result.provider, 'value') else result.provider,
            direction=result.direction.value if hasattr(result.direction, 'value') else result.direction,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            webhook_url=webhook_url,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(f"Invalid enum value: {str(e)}")
        )
    except MimicError as e:
        handle_mimic_error(e)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "delete")),
):
    """Delete an integration.

    Proxies to Mimic integration service (soft delete).
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        await use_cases.delete_integration(
            integration_id=integration_id,
            token=token,
        )

        logger.info(
            "Integration deleted via Mimic",
            integration_id=integration_id,
            user_id=user.id,
        )

    except MimicError as e:
        handle_mimic_error(e)


# === Credential Endpoints ===

@router.post("/{integration_id}/credentials", status_code=status.HTTP_201_CREATED)
async def add_credential(
    integration_id: str,
    request: CredentialRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Add a credential to an integration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        credential_type = CredentialType(request.credential_type)

        result = await use_cases.add_credential(
            integration_id=integration_id,
            credential=CredentialCreate(
                credential_type=credential_type,
                value=request.value,
                credential_metadata=request.metadata,
                expires_at=request.expires_at,
            ),
            token=token,
        )

        logger.info(
            "Credential added via Mimic",
            integration_id=integration_id,
            credential_id=result.get("id"),
            user_id=user.id,
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(f"Invalid credential type: {str(e)}")
        )
    except MimicError as e:
        handle_mimic_error(e)


# === Inbound Config Endpoints ===

@router.put("/{integration_id}/inbound")
async def set_inbound_config(
    integration_id: str,
    request: InboundConfigRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Set inbound webhook configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        auth_method = InboundAuthMethod(request.auth_method)
        destination_service = DestinationService(request.destination_service)

        result = await use_cases.set_inbound_config(
            integration_id=integration_id,
            config=InboundConfigCreate(
                webhook_path=request.webhook_path,
                auth_method=auth_method,
                signature_secret=request.signature_secret,
                event_filters=request.event_filters,
                transform_template=request.transform_template,
                destination_service=destination_service,
                destination_config=request.destination_config,
            ),
            token=token,
        )

        logger.info(
            "Inbound config set via Mimic",
            integration_id=integration_id,
            webhook_path=result.get("webhook_path"),
            user_id=user.id,
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(f"Invalid enum value: {str(e)}")
        )
    except MimicError as e:
        handle_mimic_error(e)


@router.get("/{integration_id}/inbound")
async def get_inbound_config(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """Get inbound webhook configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        return await use_cases.get_inbound_config(
            integration_id=integration_id,
            token=token,
        )

    except MimicError as e:
        handle_mimic_error(e)


@router.delete("/{integration_id}/inbound", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbound_config(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Delete inbound webhook configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        await use_cases.delete_inbound_config(
            integration_id=integration_id,
            token=token,
        )

        logger.info(
            "Inbound config deleted via Mimic",
            integration_id=integration_id,
            user_id=user.id,
        )

    except MimicError as e:
        handle_mimic_error(e)


# === Outbound Config Endpoints ===

@router.put("/{integration_id}/outbound")
async def set_outbound_config(
    integration_id: str,
    request: OutboundConfigRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Set outbound action configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        action_type = OutboundActionType(request.action_type)

        result = await use_cases.set_outbound_config(
            integration_id=integration_id,
            config=OutboundConfigCreate(
                action_type=action_type,
                default_template=request.default_template,
                rate_limit_requests=request.rate_limit_requests,
                rate_limit_window_seconds=request.rate_limit_window_seconds,
            ),
            token=token,
        )

        logger.info(
            "Outbound config set via Mimic",
            integration_id=integration_id,
            action_type=request.action_type,
            user_id=user.id,
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(f"Invalid action type: {str(e)}")
        )
    except MimicError as e:
        handle_mimic_error(e)


@router.get("/{integration_id}/outbound")
async def get_outbound_config(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """Get outbound action configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        return await use_cases.get_outbound_config(
            integration_id=integration_id,
            token=token,
        )

    except MimicError as e:
        handle_mimic_error(e)


@router.delete("/{integration_id}/outbound", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outbound_config(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Delete outbound action configuration.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        await use_cases.delete_outbound_config(
            integration_id=integration_id,
            token=token,
        )

        logger.info(
            "Outbound config deleted via Mimic",
            integration_id=integration_id,
            user_id=user.id,
        )

    except MimicError as e:
        handle_mimic_error(e)


# === Action Execution Endpoint ===

@router.post("/{integration_id}/actions/{action_type}")
async def execute_action(
    integration_id: str,
    action_type: str,
    request: ExecuteActionRequest,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "execute")),
):
    """Execute an outbound action.

    Proxies to Mimic integration service.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        # Build params from request
        params = request.model_dump(exclude_none=True)

        result = await use_cases.execute_action(
            integration_id=integration_id,
            action_type=action_type,
            params=params,
            token=token,
        )

        logger.info(
            "Action executed via Mimic",
            integration_id=integration_id,
            action_type=action_type,
            success=result.success,
            user_id=user.id,
        )

        return result.model_dump()

    except MimicError as e:
        handle_mimic_error(e)


# === Webhook URL Endpoint ===

@router.get("/{integration_id}/webhook-url")
async def get_webhook_url(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """Get the inbound webhook URL for an integration.

    The webhook URL is managed by Mimic and points to the Mimic gateway.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        webhook_url = await use_cases.get_inbound_webhook_url(
            integration_id=integration_id,
            token=token,
        )

        return {
            "integration_id": integration_id,
            "webhook_url": webhook_url,
        }

    except MimicError as e:
        handle_mimic_error(e)


# === Integration Events SSE Endpoint ===

@router.get("/{integration_id}/events")
async def integration_events_stream(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """
    SSE stream of integration events.

    Streams real-time events for this integration from the event bus.
    Events include incoming webhooks, outbound actions, and errors.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()
    event_stream_use_cases = _get_integration_event_stream_use_cases()

    # Verify integration exists and user has access
    try:
        await use_cases.get_integration(
            integration_id=integration_id,
            token=token,
        )
    except MimicError as e:
        handle_mimic_error(e)

    return StreamingResponse(
        event_stream_use_cases.stream_events(integration_id=integration_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# === Inbound Config Test Endpoint ===

@router.post("/{integration_id}/inbound/test")
async def test_inbound_config(
    integration_id: str,
    http_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "view")),
):
    """Test/validate inbound webhook configuration.

    Proxies to Mimic's inbound config test endpoint.
    """
    token = get_bearer_token(http_request)
    use_cases = _get_integration_use_cases()

    try:
        return await use_cases.test_inbound_config(
            integration_id=integration_id,
            token=token,
        )

    except MimicError as e:
        handle_mimic_error(e)


# =============================================================================
# Internal Integration Event Receiver (service-to-service)
# =============================================================================

# Separate router for internal endpoints (no user auth — uses shared secret)
internal_router = APIRouter(prefix="/api/internal", tags=["internal"])

# Shared secret for Mimic → Tentackl communication
MIMIC_INTERNAL_KEY = os.getenv("MIMIC_INTERNAL_KEY", os.getenv("MIMIC_SERVICE_API_KEY", ""))


class IntegrationEventPayload(BaseModel):
    """Payload from Mimic's route_integration_event Celery task."""
    event_id: str
    integration_id: str
    organization_id: str
    event_type: str
    data: dict
    interaction_token: Optional[str] = None
    application_id: Optional[str] = None


@internal_router.post("/integration-events")
async def receive_integration_event(
    request: IntegrationEventPayload,
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
):
    """Receive a routed integration event from Mimic.

    This is a service-to-service endpoint. Mimic routes inbound webhook
    events here after gateway authentication and payload transformation.

    The event is published to the Redis event bus for consumption by
    workflows and agents.
    """
    # Validate internal key
    if not MIMIC_INTERNAL_KEY:
        logger.warning("MIMIC_INTERNAL_KEY not configured, rejecting request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal key not configured",
        )
    if x_internal_key != MIMIC_INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal key",
        )

    # Publish to event bus
    from src.api.routers.event_bus import get_event_bus
    from src.interfaces.event_bus import Event, EventSourceType

    bus = get_event_bus()

    event = Event(
        source=f"integration:{request.integration_id}",
        source_type=EventSourceType.WEBHOOK,
        event_type=f"external.integration.{request.event_type}",
        data=request.data,
        metadata={
            "event_id": request.event_id,
            "integration_id": request.integration_id,
            "organization_id": request.organization_id,
            "source_id": f"integration:{request.integration_id}",  # For EventTriggerWorker lookup
            **({"interaction_token": request.interaction_token} if request.interaction_token else {}),
            **({"application_id": request.application_id} if request.application_id else {}),
        },
    )

    published = await bus.publish(event)
    if not published:
        logger.error(
            "failed_to_publish_integration_event",
            event_id=request.event_id,
            integration_id=request.integration_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish event",
        )

    # Also publish to integration-specific SSE channel for live streaming
    try:
        event_stream_use_cases = _get_integration_event_stream_use_cases()
        sse_event = {
            "type": f"integration.{request.event_type}",
            "event_id": request.event_id,
            "integration_id": request.integration_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {
                "event_type": request.event_type,
                "preview": str(request.data)[:200] if request.data else None,
            },
        }
        await event_stream_use_cases.publish_event(
            integration_id=request.integration_id,
            event=sse_event,
        )
    except Exception as e:
        logger.warning(
            "Failed to publish to SSE channel (non-fatal)",
            integration_id=request.integration_id,
            error=str(e),
        )

    logger.info(
        "integration_event_received_and_published",
        event_id=request.event_id,
        integration_id=request.integration_id,
        event_type=request.event_type,
        bus_event_id=event.id,
    )

    return {
        "status": "accepted",
        "event_id": request.event_id,
        "bus_event_id": event.id,
    }
