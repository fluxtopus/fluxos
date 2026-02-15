"""
inkPass SDK - Official Python SDK for inkPass Authentication & Authorization

This SDK provides a simple, typed interface for integrating with the inkPass
authentication and authorization service.

Example:
    ```python
    from inkpass_sdk import InkPassClient, InkPassConfig

    # Initialize client
    config = InkPassConfig(base_url="http://inkpass:8000")
    client = InkPassClient(config)

    # Authenticate user
    tokens = await client.login("user@example.com", "password")

    # Validate token
    user = await client.validate_token(tokens["access_token"])

    # Check permission
    can_create = await client.check_permission(
        tokens["access_token"],
        resource="workflows",
        action="create"
    )
    ```

Permission Checking (FastAPI):
    ```python
    from inkpass_sdk import InkPassClient
    from inkpass_sdk.permissions import PermissionChecker

    client = InkPassClient(config)
    permissions = PermissionChecker(client)

    @router.post("/workflows")
    async def create_workflow(
        _: None = Depends(permissions.require("workflows", "create")),
    ):
        ...
    ```
"""

from .client import InkPassClient
from .config import InkPassConfig
from .exceptions import (
    InkPassError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from .files import FileClient
from .models import (
    APIKeyInfoResponse,
    BillingConfigResponse,
    CheckoutResponse,
    PermissionCheckResponse,
    PermissionResponse,
    RegistrationResponse,
    SubscriptionResponse,
    TokenResponse,
    UserResponse,
)
from .permissions import PermissionChecker, create_permission_checker
from .dev_permissions import (
    ALL_PERMISSIONS,
    ROLE_PRESETS,
    TENTACKL_PERMISSIONS,
    MIMIC_PERMISSIONS,
    AIOS_PERMISSIONS,
    INKPASS_PERMISSIONS,
    get_permissions_for_preset,
    get_permissions_for_service,
    get_new_permissions,
)
from .version import __version__

__all__ = [
    # Clients
    "InkPassClient",
    "FileClient",
    "InkPassConfig",
    # Permission Utilities
    "PermissionChecker",
    "create_permission_checker",
    # Permission Definitions
    "ALL_PERMISSIONS",
    "ROLE_PRESETS",
    "TENTACKL_PERMISSIONS",
    "MIMIC_PERMISSIONS",
    "AIOS_PERMISSIONS",
    "INKPASS_PERMISSIONS",
    "get_permissions_for_preset",
    "get_permissions_for_service",
    "get_new_permissions",
    # Exceptions
    "InkPassError",
    "AuthenticationError",
    "PermissionDeniedError",
    "RateLimitError",
    "ResourceNotFoundError",
    "ServiceUnavailableError",
    "ValidationError",
    # Models
    "APIKeyInfoResponse",
    "BillingConfigResponse",
    "CheckoutResponse",
    "PermissionCheckResponse",
    "PermissionResponse",
    "RegistrationResponse",
    "SubscriptionResponse",
    "TokenResponse",
    "UserResponse",
    # Version
    "__version__",
]
