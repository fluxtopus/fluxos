"""Mimic Python SDK

Provides async clients for Mimic Notification and Integration services.

Example:
    ```python
    from mimic import (
        MimicClient,
        MimicIntegrationClient,
        MimicConfig,
        IntegrationProvider,
        IntegrationDirection,
    )

    # Notification client
    client = MimicClient(api_key="your-api-key")
    await client.send_notification(
        recipient="user@example.com",
        content="Hello!",
        provider="email"
    )

    # Integration client
    config = MimicConfig(base_url="http://mimic:8000")
    async with MimicIntegrationClient(config) as client:
        integrations = await client.list_integrations(token="jwt-token")

        # Execute Discord action
        result = await client.execute_action(
            "integration-id",
            "send_message",
            {"content": "Hello from Mimic!"},
            token="jwt-token"
        )
    ```
"""

from .client import MimicClient
from .config import MimicConfig
from .exceptions import (
    AuthenticationError,
    MimicError,
    PermissionDeniedError,
    RateLimitError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from .integration_client import MimicIntegrationClient
from .models import (
    ActionExecuteRequest,
    ActionExecuteResponse,
    Credential,
    CredentialCreate,
    CredentialSummary,
    CredentialTestResult,
    CredentialType,
    CredentialUpdate,
    DestinationService,
    InboundAuthMethod,
    InboundConfig,
    InboundConfigCreate,
    InboundConfigSummary,
    Integration,
    IntegrationCreate,
    IntegrationDetail,
    IntegrationDirection,
    IntegrationListResponse,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationUpdate,
    OutboundActionType,
    OutboundConfig,
    OutboundConfigCreate,
    OutboundConfigSummary,
)

__version__ = "0.1.2"

__all__ = [
    # Version
    "__version__",
    # Clients
    "MimicClient",
    "MimicIntegrationClient",
    # Configuration
    "MimicConfig",
    # Exceptions
    "MimicError",
    "AuthenticationError",
    "PermissionDeniedError",
    "ResourceNotFoundError",
    "ValidationError",
    "RateLimitError",
    "ServiceUnavailableError",
    # Enums
    "IntegrationProvider",
    "IntegrationDirection",
    "IntegrationStatus",
    "CredentialType",
    "InboundAuthMethod",
    "DestinationService",
    "OutboundActionType",
    # Integration Models
    "Integration",
    "IntegrationCreate",
    "IntegrationUpdate",
    "IntegrationDetail",
    "IntegrationListResponse",
    # Credential Models
    "Credential",
    "CredentialCreate",
    "CredentialUpdate",
    "CredentialSummary",
    "CredentialTestResult",
    # Inbound Config Models
    "InboundConfig",
    "InboundConfigCreate",
    "InboundConfigSummary",
    # Outbound Config Models
    "OutboundConfig",
    "OutboundConfigCreate",
    "OutboundConfigSummary",
    # Action Models
    "ActionExecuteRequest",
    "ActionExecuteResponse",
]
