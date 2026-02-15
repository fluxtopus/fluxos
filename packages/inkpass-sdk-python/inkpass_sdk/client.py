"""inkPass SDK Client implementation."""

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import InkPassConfig
from .exceptions import (
    AuthenticationError,
    InkPassError,
    PermissionDeniedError,
    RateLimitError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from .models import (
    APIKeyInfoResponse,
    APIKeyResponse,
    BillingConfigResponse,
    CheckoutResponse,
    GroupResponse,
    OrganizationResponse,
    PermissionCheckResponse,
    PermissionResponse,
    RegistrationResponse,
    SubscriptionResponse,
    TokenResponse,
    UserResponse,
)

logger = structlog.get_logger()


class InkPassClient:
    """
    Async client for inkPass authentication and authorization service.

    This client provides a typed, easy-to-use interface for all inkPass operations.
    All I/O operations are async and include automatic retry logic.

    Example:
        ```python
        from inkpass_sdk import InkPassClient, InkPassConfig

        # Initialize
        config = InkPassConfig(base_url="http://inkpass:8000")
        client = InkPassClient(config)

        # Login
        tokens = await client.login("user@example.com", "password")

        # Check permission
        can_create = await client.check_permission(
            tokens.access_token,
            "workflows",
            "create"
        )
        ```
    """

    def __init__(self, config: InkPassConfig | None = None) -> None:
        """
        Initialize inkPass client.

        Args:
            config: Client configuration. If None, uses default config.
        """
        self.config = config or InkPassConfig()
        self._client: httpx.AsyncClient | None = None
        logger.info("InkPassClient initialized", base_url=self.config.base_url)

    async def __aenter__(self) -> "InkPassClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
            )
        return self._client

    def _get_headers(self, token: str | None = None) -> dict[str, str]:
        """
        Get request headers.

        Args:
            token: Optional JWT token for authentication

        Returns:
            Headers dictionary
        """
        headers = {"Content-Type": "application/json"}

        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.config.api_key:
            headers["X-API-Key"] = self.config.api_key

        return headers

    def _handle_error(self, response: httpx.Response) -> None:
        """
        Handle HTTP error responses.

        Args:
            response: HTTP response

        Raises:
            AuthenticationError: For 401 responses
            PermissionDeniedError: For 403 responses
            ResourceNotFoundError: For 404 responses
            ValidationError: For 422 responses
            ServiceUnavailableError: For 503 responses
            InkPassError: For other errors
        """
        status_code = response.status_code

        try:
            error_data = response.json()
            message = error_data.get("detail", response.text)
        except Exception:
            message = response.text

        if status_code == 400:
            raise ValidationError(message)
        elif status_code == 401:
            raise AuthenticationError(message)
        elif status_code == 403:
            raise PermissionDeniedError(message)
        elif status_code == 404:
            raise ResourceNotFoundError(message)
        elif status_code == 422:
            raise ValidationError(message)
        elif status_code == 429:
            raise RateLimitError(message)
        elif status_code == 503:
            raise ServiceUnavailableError(message)
        else:
            raise InkPassError(message, status_code=status_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def register(
        self,
        email: str,
        password: str,
        organization_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> RegistrationResponse:
        """
        Register a new user.

        Args:
            email: User email
            password: User password
            organization_name: Optional organization name (auto-generated if not provided)
            first_name: User first name
            last_name: User last name

        Returns:
            RegistrationResponse with user_id, email, organization_id

        Raises:
            ValidationError: If input validation fails
            InkPassError: If registration fails
        """
        try:
            client = self._get_client()
            data: dict[str, Any] = {
                "email": email,
                "password": password,
            }
            if organization_name:
                data["organization_name"] = organization_name
            if first_name:
                data["first_name"] = first_name
            if last_name:
                data["last_name"] = last_name

            response = await client.post(
                "/api/v1/auth/register",
                headers=self._get_headers(),
                json=data,
            )

            if response.status_code == 201:
                logger.info("User registered successfully", email=email)
                return RegistrationResponse(**response.json())
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Registration request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        # This should never be reached due to _handle_error
        raise InkPassError("Unexpected error during registration")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def login(self, email: str, password: str) -> TokenResponse:
        """
        Authenticate user and get tokens.

        Args:
            email: User email
            password: User password

        Returns:
            TokenResponse with access_token, refresh_token, etc.

        Raises:
            AuthenticationError: If credentials are invalid
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/api/v1/auth/login",
                headers=self._get_headers(),
                json={"email": email, "password": password},
            )

            if response.status_code == 200:
                logger.info("User logged in successfully", email=email)
                return TokenResponse(**response.json())
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Login request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during login")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def validate_token(self, token: str) -> UserResponse | None:
        """
        Validate JWT token and get user information.

        Args:
            token: JWT access token

        Returns:
            UserResponse if token is valid, None if invalid

        Raises:
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/auth/me",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                user_data = response.json()
                logger.info("Token validated successfully", user_id=user_data.get("id"))
                return UserResponse(**user_data)
            elif response.status_code == 401:
                logger.warning("Token validation failed - invalid token")
                return None
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Token validation request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def validate_api_key(self, api_key: str) -> APIKeyInfoResponse | None:
        """
        Validate an API key and get key information.

        Calls GET /api/v1/auth/me with the X-API-Key header.

        Args:
            api_key: The API key to validate

        Returns:
            APIKeyInfoResponse if key is valid, None if invalid

        Raises:
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Content-Type": "application/json", "X-API-Key": api_key},
            )

            if response.status_code == 200:
                data = response.json()
                logger.info("API key validated successfully", key_id=data.get("id"))
                return APIKeyInfoResponse(**data)
            elif response.status_code == 401:
                logger.warning("API key validation failed - invalid key")
                return None
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("API key validation request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if user has permission for resource and action.

        This method is fail-safe: returns False on errors to deny access by default.

        Args:
            token: JWT access token
            resource: Resource name (e.g., "workflows", "notifications")
            action: Action name (e.g., "create", "read", "update", "delete")
            context: Optional context for ABAC evaluation

        Returns:
            True if user has permission, False otherwise

        Note:
            This method defaults to False on errors for security (fail-safe).
        """
        try:
            client = self._get_client()
            params = {"resource": resource, "action": action}

            response = await client.post(
                "/api/v1/auth/check",
                headers=self._get_headers(token),
                params=params,
                json=context or {},
            )

            if response.status_code == 200:
                result = PermissionCheckResponse(**response.json())
                logger.info(
                    "Permission checked",
                    resource=resource,
                    action=action,
                    has_permission=result.has_permission,
                )
                return result.has_permission
            elif response.status_code == 401:
                logger.warning("Permission check failed - invalid token")
                return False
            else:
                logger.error(
                    "Permission check failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return False  # Fail-safe: deny access on error

        except httpx.RequestError as e:
            logger.error("Permission check request failed", error=str(e))
            return False  # Fail-safe: deny access if service unavailable

    async def check_permissions_batch(
        self,
        token: str,
        permissions: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """
        Check multiple permissions in batch.

        This method checks multiple resource:action pairs efficiently.

        Args:
            token: JWT access token
            permissions: List of (resource, action) tuples to check
            context: Optional context for ABAC evaluation (applied to all checks)

        Returns:
            Dictionary mapping "resource:action" to boolean result

        Note:
            This method defaults to False on errors for security (fail-safe).

        Example:
            ```python
            results = await client.check_permissions_batch(
                token,
                [("workflows", "create"), ("workflows", "delete"), ("agents", "view")]
            )
            # Returns: {"workflows:create": True, "workflows:delete": False, "agents:view": True}
            ```
        """
        results = {}
        for resource, action in permissions:
            key = f"{resource}:{action}"
            results[key] = await self.check_permission(token, resource, action, context)
        return results

    async def has_any_permission(
        self,
        token: str,
        permissions: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if user has ANY of the specified permissions.

        Args:
            token: JWT access token
            permissions: List of (resource, action) tuples
            context: Optional context for ABAC evaluation

        Returns:
            True if user has at least one of the permissions
        """
        for resource, action in permissions:
            if await self.check_permission(token, resource, action, context):
                return True
        return False

    async def has_all_permissions(
        self,
        token: str,
        permissions: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if user has ALL of the specified permissions.

        Args:
            token: JWT access token
            permissions: List of (resource, action) tuples
            context: Optional context for ABAC evaluation

        Returns:
            True if user has all of the permissions
        """
        for resource, action in permissions:
            if not await self.check_permission(token, resource, action, context):
                return False
        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def list_user_permissions(self, token: str) -> list[PermissionResponse]:
        """
        List all permissions assigned to the current user.

        Args:
            token: JWT access token

        Returns:
            List of PermissionResponse objects

        Raises:
            AuthenticationError: If token is invalid
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/permissions",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                data = response.json()
                return [PermissionResponse(**p) for p in data]
            elif response.status_code == 401:
                raise AuthenticationError("Invalid token")
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("List permissions request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        return []

    async def get_user_info(self, token: str) -> UserResponse | None:
        """
        Get user information (alias for validate_token).

        Args:
            token: JWT access token

        Returns:
            UserResponse if token is valid, None otherwise
        """
        return await self.validate_token(token)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def create_api_key(
        self, token: str, name: str, scopes: list[str] | None = None
    ) -> APIKeyResponse:
        """
        Create a new API key.

        Args:
            token: JWT access token
            name: API key name
            scopes: Optional list of scopes for the key

        Returns:
            APIKeyResponse with the created key (only shown once)

        Raises:
            AuthenticationError: If token is invalid
            ValidationError: If input validation fails
        """
        try:
            client = self._get_client()
            data: dict[str, Any] = {"name": name}
            if scopes:
                data["scopes"] = scopes

            response = await client.post(
                "/api/v1/api-keys",
                headers=self._get_headers(token),
                json=data,
            )

            if response.status_code in (200, 201):
                logger.info("API key created", name=name)
                return APIKeyResponse(**response.json())
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("API key creation failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during API key creation")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def verify_email(self, email: str, code: str) -> dict[str, Any]:
        """
        Verify email address with OTP code.

        Args:
            email: User email
            code: 6-digit verification code

        Returns:
            Response with verification message

        Raises:
            ValidationError: If code is invalid or expired
            ResourceNotFoundError: If user not found
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/api/v1/auth/verify-email",
                headers=self._get_headers(),
                json={"email": email, "code": code},
            )

            if response.status_code == 200:
                logger.info("Email verified successfully", email=email)
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Email verification request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during email verification")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def resend_verification(self, email: str) -> dict[str, Any]:
        """
        Resend email verification code.

        Args:
            email: User email

        Returns:
            Response with message

        Raises:
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/api/v1/auth/resend-verification",
                headers=self._get_headers(),
                json={"email": email},
            )

            if response.status_code == 200:
                logger.info("Verification code resent", email=email)
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Resend verification request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during resend verification")

    # === Billing Methods ===

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def configure_billing(
        self,
        stripe_api_key: str,
        stripe_webhook_secret: str | None = None,
        prices: dict[str, str] | None = None,
    ) -> BillingConfigResponse:
        """
        Configure Stripe billing for the organization.

        This method is typically called by parent services (e.g., a control-plane service)
        to set up billing for their organizations. Requires API key authentication.

        Args:
            stripe_api_key: Stripe API key (sk_test_... or sk_live_...)
            stripe_webhook_secret: Stripe webhook signing secret (optional)
            prices: Price ID mapping (e.g., {"pro": "price_xxx"})

        Returns:
            BillingConfigResponse with configuration details

        Raises:
            PermissionDeniedError: If not using API key authentication
            ValidationError: If configuration is invalid
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            data: dict[str, Any] = {"stripe_api_key": stripe_api_key}
            if stripe_webhook_secret:
                data["stripe_webhook_secret"] = stripe_webhook_secret
            if prices:
                data["prices"] = prices

            response = await client.post(
                "/api/v1/billing/configure",
                headers=self._get_headers(),
                json=data,
            )

            if response.status_code == 200:
                logger.info("Billing configured successfully")
                return BillingConfigResponse(**response.json())
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Billing configuration request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during billing configuration")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def create_checkout(
        self,
        token: str,
        price_key: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutResponse:
        """
        Create a Stripe checkout session.

        Args:
            token: JWT access token
            price_key: Price key (e.g., "pro", "enterprise")
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            metadata: Optional metadata for the session

        Returns:
            CheckoutResponse with session ID and checkout URL

        Raises:
            AuthenticationError: If token is invalid
            ValidationError: If price key is not configured
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            data: dict[str, Any] = {
                "price_key": price_key,
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
            if metadata:
                data["metadata"] = metadata

            response = await client.post(
                "/api/v1/billing/checkout",
                headers=self._get_headers(token),
                json=data,
            )

            if response.status_code == 201:
                logger.info("Checkout session created", price_key=price_key)
                return CheckoutResponse(**response.json())
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Checkout creation request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during checkout creation")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_subscription(self, token: str) -> SubscriptionResponse:
        """
        Get current subscription status.

        Args:
            token: JWT access token

        Returns:
            SubscriptionResponse with status and tier information

        Raises:
            AuthenticationError: If token is invalid
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/billing/subscription",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                data = response.json()
                # Parse ends_at if present
                if data.get("ends_at"):
                    from datetime import datetime
                    data["ends_at"] = datetime.fromisoformat(data["ends_at"].replace("Z", "+00:00"))
                return SubscriptionResponse(**data)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get subscription request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error getting subscription")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_billing_portal_url(self, token: str, return_url: str) -> str:
        """
        Get Stripe billing portal URL for managing subscription.

        Args:
            token: JWT access token
            return_url: URL to return to after portal session

        Returns:
            Billing portal URL

        Raises:
            AuthenticationError: If token is invalid
            ValidationError: If no Stripe customer ID exists
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/api/v1/billing/portal",
                headers=self._get_headers(token),
                json={"return_url": return_url},
            )

            if response.status_code == 200:
                data = response.json()
                return data["url"]
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Billing portal request failed", error=str(e))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error getting billing portal URL")

    async def is_billing_configured(self) -> bool:
        """
        Check if billing is configured for the organization.

        Uses API key authentication.

        Returns:
            True if billing is configured, False otherwise
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/billing/configured",
                headers=self._get_headers(),
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("configured", False)
            else:
                return False

        except Exception as e:
            logger.error("Billing config check failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("InkPassClient closed")
