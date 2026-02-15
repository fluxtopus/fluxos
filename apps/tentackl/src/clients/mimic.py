"""Mimic Integration client for Tentackl.

This module provides a singleton Mimic client for integration management
throughout the Tentackl application.

Mimic is the central integration registry and gateway. All external service
integrations (Discord, Slack, GitHub, Stripe, custom webhooks) are managed
through Mimic. Tentackl uses the Mimic SDK to:
- List/create/update/delete integrations
- Execute outbound actions (send messages, post webhooks)
- Get inbound webhook URLs
"""

import os
import structlog
from typing import Optional, Dict, Any, List

try:
    from mimic import (
        MimicIntegrationClient,
        MimicConfig,
        MimicError,
        AuthenticationError,
        PermissionDeniedError,
        RateLimitError,
        ResourceNotFoundError,
        ServiceUnavailableError,
        ValidationError,
        IntegrationProvider,
        IntegrationDirection,
        IntegrationStatus,
    )
    from mimic.models import (
        Integration,
        IntegrationCreate,
        IntegrationDetail,
        IntegrationListResponse,
        IntegrationUpdate,
        InboundConfigCreate,
        OutboundConfigCreate,
        CredentialCreate,
        CredentialType,
        InboundAuthMethod,
        DestinationService,
        OutboundActionType,
        ActionExecuteRequest,
        ActionExecuteResponse,
    )
    _MIMIC_AVAILABLE = True
except ImportError:  # pragma: no cover - environment-specific
    _MIMIC_AVAILABLE = False
    import sys
    import types
    from enum import Enum
    from dataclasses import dataclass

    class MimicError(Exception):
        """Base Mimic error when SDK is unavailable."""

    class AuthenticationError(MimicError):
        pass

    class PermissionDeniedError(MimicError):
        pass

    class RateLimitError(MimicError):
        pass

    class ResourceNotFoundError(MimicError):
        pass

    class ServiceUnavailableError(MimicError):
        pass

    class ValidationError(MimicError):
        pass

    class MimicConfig:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            pass

    class MimicIntegrationClient:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise RuntimeError("Mimic SDK is not installed")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class IntegrationProvider(str, Enum):
        discord = "discord"
        slack = "slack"
        github = "github"
        stripe = "stripe"
        custom_webhook = "custom_webhook"

    class IntegrationDirection(str, Enum):
        inbound = "inbound"
        outbound = "outbound"
        bidirectional = "bidirectional"

    class IntegrationStatus(str, Enum):
        active = "active"
        paused = "paused"
        error = "error"

    class CredentialType(str, Enum):
        api_key = "api_key"
        webhook_url = "webhook_url"
        oauth_token = "oauth_token"
        bot_token = "bot_token"
        webhook_secret = "webhook_secret"

    class InboundAuthMethod(str, Enum):
        none = "none"
        api_key = "api_key"
        signature = "signature"
        ed25519 = "ed25519"
        bearer = "bearer"

    class DestinationService(str, Enum):
        tentackl = "tentackl"
        custom = "custom"

    class OutboundActionType(str, Enum):
        send_message = "send_message"
        send_embed = "send_embed"
        send_blocks = "send_blocks"
        create_issue = "create_issue"
        post = "post"
        put = "put"

    @dataclass
    class Integration:
        id: str
        name: str
        provider: IntegrationProvider
        direction: IntegrationDirection
        status: IntegrationStatus
        created_at: Optional[float] = None
        updated_at: Optional[float] = None

    @dataclass
    class IntegrationCreate:
        name: str
        provider: IntegrationProvider
        direction: IntegrationDirection

    @dataclass
    class IntegrationDetail:
        id: str
        name: str
        provider: IntegrationProvider
        direction: IntegrationDirection
        status: IntegrationStatus

    @dataclass
    class IntegrationListResponse:
        items: List[Integration]
        total: int

    @dataclass
    class IntegrationUpdate:
        name: Optional[str] = None
        status: Optional[IntegrationStatus] = None

    @dataclass
    class InboundConfigCreate:
        webhook_path: Optional[str] = None

    @dataclass
    class OutboundConfigCreate:
        action_type: Optional[OutboundActionType] = None

    @dataclass
    class CredentialCreate:
        credential_type: CredentialType
        value: str

    @dataclass
    class ActionExecuteRequest:
        content: Optional[str] = None

    @dataclass
    class ActionExecuteResponse:
        success: bool
        message: Optional[str] = None

    # Register stub modules so "import mimic" works in tests when SDK is absent.
    _stub = types.ModuleType("mimic")
    _stub_models = types.ModuleType("mimic.models")
    for name, value in {
        "MimicIntegrationClient": MimicIntegrationClient,
        "MimicConfig": MimicConfig,
        "MimicError": MimicError,
        "AuthenticationError": AuthenticationError,
        "PermissionDeniedError": PermissionDeniedError,
        "RateLimitError": RateLimitError,
        "ResourceNotFoundError": ResourceNotFoundError,
        "ServiceUnavailableError": ServiceUnavailableError,
        "ValidationError": ValidationError,
        "IntegrationProvider": IntegrationProvider,
        "IntegrationDirection": IntegrationDirection,
        "IntegrationStatus": IntegrationStatus,
        "CredentialType": CredentialType,
        "InboundAuthMethod": InboundAuthMethod,
        "DestinationService": DestinationService,
        "OutboundActionType": OutboundActionType,
    }.items():
        setattr(_stub, name, value)

    for name, value in {
        "Integration": Integration,
        "IntegrationCreate": IntegrationCreate,
        "IntegrationDetail": IntegrationDetail,
        "IntegrationListResponse": IntegrationListResponse,
        "IntegrationUpdate": IntegrationUpdate,
        "InboundConfigCreate": InboundConfigCreate,
        "OutboundConfigCreate": OutboundConfigCreate,
        "CredentialCreate": CredentialCreate,
        "ActionExecuteRequest": ActionExecuteRequest,
        "ActionExecuteResponse": ActionExecuteResponse,
        "CredentialType": CredentialType,
        "InboundAuthMethod": InboundAuthMethod,
        "DestinationService": DestinationService,
        "OutboundActionType": OutboundActionType,
    }.items():
        setattr(_stub_models, name, value)

    sys.modules.setdefault("mimic", _stub)
    sys.modules.setdefault("mimic.models", _stub_models)

logger = structlog.get_logger()

# Configuration from environment
MIMIC_URL = os.getenv("MIMIC_URL", "http://mimic:8000")
MIMIC_TIMEOUT = float(os.getenv("MIMIC_TIMEOUT", "10.0"))
MIMIC_MAX_RETRIES = int(os.getenv("MIMIC_MAX_RETRIES", "3"))

def _require_mimic() -> None:
    if not _MIMIC_AVAILABLE:
        raise RuntimeError("Mimic SDK is not installed; integrations are unavailable.")


if _MIMIC_AVAILABLE:
    # Initialize Mimic SDK configuration
    mimic_config = MimicConfig(
        base_url=MIMIC_URL,
        timeout=MIMIC_TIMEOUT,
        max_retries=MIMIC_MAX_RETRIES,
        verify_ssl=True,
    )

    # Create singleton client instance
    mimic_client = MimicIntegrationClient(mimic_config)

    logger.info(
        "Mimic client initialized",
        base_url=MIMIC_URL,
        timeout=MIMIC_TIMEOUT,
        max_retries=MIMIC_MAX_RETRIES,
    )
else:
    mimic_config = None
    mimic_client = None
    logger.warning("Mimic SDK not installed; integrations disabled")


def get_client() -> MimicIntegrationClient:
    """
    Get a MimicIntegrationClient instance for use with async context manager.

    Usage:
        async with get_client() as client:
            integrations = await client.list_integrations(token=token)

    Returns:
        MimicIntegrationClient configured for this service
    """
    _require_mimic()
    return MimicIntegrationClient(mimic_config)


async def list_integrations(
    token: str,
    provider: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
) -> IntegrationListResponse:
    """
    List integrations from Mimic.

    Args:
        token: JWT access token
        provider: Optional filter by provider
        direction: Optional filter by direction
        status: Optional filter by status

    Returns:
        IntegrationListResponse with items and total count

    Raises:
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.list_integrations(
                provider=provider,
                direction=direction,
                status=status,
                token=token,
            )
            logger.debug(
                "Integrations listed",
                count=result.total,
                provider=provider,
            )
            return result
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to list integrations", error=str(e))
        raise


async def get_integration(
    integration_id: str,
    token: str,
) -> IntegrationDetail:
    """
    Get integration details from Mimic.

    Args:
        integration_id: Integration ID
        token: JWT access token

    Returns:
        IntegrationDetail with full configuration

    Raises:
        ResourceNotFoundError: If integration not found
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.get_integration(
                integration_id=integration_id,
                token=token,
            )
            logger.debug("Integration retrieved", integration_id=integration_id)
            return result
    except ResourceNotFoundError:
        logger.warning("Integration not found", integration_id=integration_id)
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to get integration", error=str(e))
        raise


async def create_integration(
    data: IntegrationCreate,
    token: str,
) -> Integration:
    """
    Create a new integration in Mimic.

    Args:
        data: Integration creation data
        token: JWT access token

    Returns:
        Created Integration

    Raises:
        ValidationError: If input validation fails
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.create_integration(
                data=data,
                token=token,
            )
            logger.info("Integration created", integration_id=result.id)
            return result
    except ValidationError as e:
        logger.warning("Integration creation validation failed", error=str(e))
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to create integration", error=str(e))
        raise


async def update_integration(
    integration_id: str,
    data: IntegrationUpdate,
    token: str,
) -> Integration:
    """
    Update an integration in Mimic.

    Args:
        integration_id: Integration ID
        data: Update data
        token: JWT access token

    Returns:
        Updated Integration

    Raises:
        ResourceNotFoundError: If integration not found
        ValidationError: If input validation fails
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.update_integration(
                integration_id=integration_id,
                data=data,
                token=token,
            )
            logger.info("Integration updated", integration_id=integration_id)
            return result
    except (ResourceNotFoundError, ValidationError):
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to update integration", error=str(e))
        raise


async def delete_integration(
    integration_id: str,
    token: str,
) -> bool:
    """
    Delete an integration in Mimic.

    Args:
        integration_id: Integration ID
        token: JWT access token

    Returns:
        True if successfully deleted

    Raises:
        ResourceNotFoundError: If integration not found
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.delete_integration(
                integration_id=integration_id,
                token=token,
            )
            logger.info("Integration deleted", integration_id=integration_id)
            return result
    except ResourceNotFoundError:
        logger.warning("Integration not found", integration_id=integration_id)
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to delete integration", error=str(e))
        raise


async def execute_action(
    integration_id: str,
    action_type: str,
    params: Dict[str, Any],
    token: str,
) -> ActionExecuteResponse:
    """
    Execute an outbound action via Mimic.

    Args:
        integration_id: Integration ID
        action_type: Action type (send_message, send_embed, etc.)
        params: Action parameters
        token: JWT access token

    Returns:
        ActionExecuteResponse with result or job_id

    Raises:
        ResourceNotFoundError: If integration not found
        ValidationError: If action type or parameters invalid
        RateLimitError: If rate limit exceeded
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.execute_action(
                integration_id=integration_id,
                action_type=action_type,
                params=params,
                token=token,
            )
            logger.info(
                "Action executed",
                integration_id=integration_id,
                action_type=action_type,
                success=result.success,
            )
            return result
    except (ResourceNotFoundError, ValidationError, RateLimitError):
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to execute action", error=str(e))
        raise


async def get_inbound_webhook_url(
    integration_id: str,
    token: str,
) -> str:
    """
    Get the inbound webhook URL for an integration from Mimic.

    Args:
        integration_id: Integration ID
        token: JWT access token

    Returns:
        Full webhook URL

    Raises:
        ResourceNotFoundError: If integration or inbound config not found
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.get_inbound_webhook_url(
                integration_id=integration_id,
                token=token,
            )
            logger.debug(
                "Inbound webhook URL retrieved",
                integration_id=integration_id,
                webhook_url=result,
            )
            return result
    except ResourceNotFoundError:
        logger.warning(
            "Inbound config not found",
            integration_id=integration_id,
        )
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to get inbound webhook URL", error=str(e))
        raise


async def set_inbound_config(
    integration_id: str,
    config: InboundConfigCreate,
    token: str,
) -> Dict[str, Any]:
    """
    Set inbound webhook configuration for an integration.

    Args:
        integration_id: Integration ID
        config: Inbound config data
        token: JWT access token

    Returns:
        InboundConfig with full webhook URL

    Raises:
        ResourceNotFoundError: If integration not found
        ValidationError: If config invalid or direction is outbound-only
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.set_inbound_config(
                integration_id=integration_id,
                data=config,
                token=token,
            )
            logger.info(
                "Inbound config set",
                integration_id=integration_id,
                webhook_path=result.webhook_path,
            )
            return result.model_dump()
    except (ResourceNotFoundError, ValidationError):
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to set inbound config", error=str(e))
        raise


async def set_outbound_config(
    integration_id: str,
    config: OutboundConfigCreate,
    token: str,
) -> Dict[str, Any]:
    """
    Set outbound action configuration for an integration.

    Args:
        integration_id: Integration ID
        config: Outbound config data
        token: JWT access token

    Returns:
        OutboundConfig

    Raises:
        ResourceNotFoundError: If integration not found
        ValidationError: If action type not supported or direction is inbound-only
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.set_outbound_config(
                integration_id=integration_id,
                data=config,
                token=token,
            )
            logger.info(
                "Outbound config set",
                integration_id=integration_id,
                action_type=result.action_type,
            )
            return result.model_dump()
    except (ResourceNotFoundError, ValidationError):
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to set outbound config", error=str(e))
        raise


async def add_credential(
    integration_id: str,
    credential: CredentialCreate,
    token: str,
) -> Dict[str, Any]:
    """
    Add a credential to an integration.

    Args:
        integration_id: Integration ID
        credential: Credential data
        token: JWT access token

    Returns:
        Created Credential (without sensitive value)

    Raises:
        ResourceNotFoundError: If integration not found
        ValidationError: If credential invalid
        ServiceUnavailableError: If Mimic service is unavailable
    """
    try:
        async with get_client() as client:
            result = await client.add_credential(
                integration_id=integration_id,
                data=credential,
                token=token,
            )
            logger.info(
                "Credential added",
                integration_id=integration_id,
                credential_id=result.id,
            )
            return result.model_dump()
    except (ResourceNotFoundError, ValidationError):
        raise
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to add credential", error=str(e))
        raise


async def send_followup(
    integration_id: str,
    interaction_token: str,
    application_id: str,
    content: str,
    token: str,
    embeds: list[dict] | None = None,
) -> dict:
    """Send a follow-up response to a Discord interaction via Mimic.

    This allows Tentackl workflows/agents to respond to Discord slash
    commands by calling Mimic's follow-up endpoint, which POSTs to
    Discord's interaction webhook.

    Args:
        integration_id: The Mimic integration ID.
        interaction_token: Discord interaction token (from event metadata).
        application_id: Discord application/bot ID (from event metadata).
        content: Text content to send.
        token: JWT access token for Mimic authentication.
        embeds: Optional list of Discord embed objects.

    Returns:
        Response dict from Mimic/Discord.

    Raises:
        ServiceUnavailableError: If Mimic service is unavailable.
    """
    try:
        async with get_client() as client:
            http_client = client._get_client()
            headers = client._get_headers(token=token)
            payload = {
                "interaction_token": interaction_token,
                "application_id": application_id,
                "content": content,
            }
            if embeds:
                payload["embeds"] = embeds

            response = await http_client.post(
                f"/api/v1/integrations/{integration_id}/followup",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                client._handle_error(response)
            result = response.json()
            logger.info(
                "Discord follow-up sent via Mimic",
                integration_id=integration_id,
                application_id=application_id,
            )
            return result
    except ServiceUnavailableError as e:
        logger.error("Mimic service unavailable for follow-up", error=str(e))
        raise
    except Exception as e:
        logger.warning("Failed to send Discord follow-up", error=str(e))
        raise


async def health_check() -> bool:
    """
    Check if Mimic service is healthy.

    Returns:
        True if service is healthy, False otherwise
    """
    try:
        async with get_client() as client:
            # Try to list integrations with a dummy token
            # If we get auth error, service is up
            await client.list_integrations(token="health-check")
            return True
    except AuthenticationError:
        # Auth error means service is up
        return True
    except ServiceUnavailableError:
        return False
    except Exception:
        # Other errors might mean service is up but something else failed
        return True


# Export all public functions and models
__all__ = [
    # Client
    "mimic_client",
    "mimic_config",
    "get_client",
    # Functions
    "list_integrations",
    "get_integration",
    "create_integration",
    "update_integration",
    "delete_integration",
    "execute_action",
    "get_inbound_webhook_url",
    "set_inbound_config",
    "set_outbound_config",
    "add_credential",
    "send_followup",
    "health_check",
    # Exceptions
    "MimicError",
    "AuthenticationError",
    "PermissionDeniedError",
    "RateLimitError",
    "ResourceNotFoundError",
    "ServiceUnavailableError",
    "ValidationError",
    # Enums
    "IntegrationProvider",
    "IntegrationDirection",
    "IntegrationStatus",
    "CredentialType",
    "InboundAuthMethod",
    "DestinationService",
    "OutboundActionType",
    # Models
    "Integration",
    "IntegrationCreate",
    "IntegrationDetail",
    "IntegrationListResponse",
    "IntegrationUpdate",
    "InboundConfigCreate",
    "OutboundConfigCreate",
    "CredentialCreate",
    "ActionExecuteRequest",
    "ActionExecuteResponse",
]
