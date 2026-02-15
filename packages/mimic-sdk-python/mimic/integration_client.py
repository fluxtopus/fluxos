"""Mimic SDK Integration Client - INT-017.

Async client for Mimic Integration management API.

Required methods:
- list_integrations(organization_id, provider=None)
- get_integration(integration_id)
- execute_action(integration_id, action_type, params)
- get_inbound_webhook_url(integration_id)
"""

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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
from .models import (
    ActionExecuteRequest,
    ActionExecuteResponse,
    Credential,
    CredentialCreate,
    CredentialTestResult,
    CredentialUpdate,
    InboundConfig,
    InboundConfigCreate,
    Integration,
    IntegrationCreate,
    IntegrationDetail,
    IntegrationListResponse,
    IntegrationUpdate,
    OutboundConfig,
    OutboundConfigCreate,
)

logger = structlog.get_logger()


class MimicIntegrationClient:
    """
    Async client for Mimic Integration management API.

    This client provides a typed, easy-to-use interface for managing integrations,
    credentials, inbound/outbound configurations, and executing outbound actions.
    All I/O operations are async and include automatic retry logic.

    Example:
        ```python
        from mimic import MimicIntegrationClient, MimicConfig

        # Initialize
        config = MimicConfig(base_url="http://mimic:8000", api_key="your-api-key")
        client = MimicIntegrationClient(config)

        # List integrations
        integrations = await client.list_integrations(
            organization_id="org-123",
            provider="discord"
        )

        # Get integration details
        integration = await client.get_integration("integration-id")

        # Execute outbound action
        result = await client.execute_action(
            "integration-id",
            "send_message",
            {"content": "Hello from Mimic!"}
        )

        # Get inbound webhook URL
        webhook_url = await client.get_inbound_webhook_url("integration-id")
        ```
    """

    def __init__(self, config: MimicConfig | None = None) -> None:
        """
        Initialize Mimic Integration client.

        Args:
            config: Client configuration. If None, uses default config.
        """
        self.config = config or MimicConfig()
        self._client: httpx.AsyncClient | None = None
        logger.info("MimicIntegrationClient initialized", base_url=self.config.base_url)

    async def __aenter__(self) -> "MimicIntegrationClient":
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
            RateLimitError: For 429 responses
            ServiceUnavailableError: For 503 responses
            MimicError: For other errors
        """
        status_code = response.status_code

        try:
            error_data = response.json()
            message = error_data.get("detail", response.text)
            # Handle rate limit specific fields
            retry_after = error_data.get("retry_after_seconds", 0)
        except Exception:
            message = response.text
            retry_after = 0

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
            raise RateLimitError(message, retry_after_seconds=retry_after)
        elif status_code == 503:
            raise ServiceUnavailableError(message)
        else:
            raise MimicError(message, status_code=status_code)

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("MimicIntegrationClient closed")

    # =========================================================================
    # Integration CRUD Methods
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def list_integrations(
        self,
        organization_id: str | None = None,
        provider: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        token: str | None = None,
    ) -> IntegrationListResponse:
        """
        List integrations, optionally filtered by provider.

        Args:
            organization_id: Organization ID to filter by (optional, inferred from auth)
            provider: Filter by provider (discord, slack, github, stripe, custom_webhook)
            direction: Filter by direction (inbound, outbound, bidirectional)
            status: Filter by status (active, paused, error)
            token: Optional JWT token for user authentication

        Returns:
            IntegrationListResponse with items and total count

        Raises:
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            params: dict[str, str] = {}
            if provider:
                params["provider"] = provider
            if direction:
                params["direction"] = direction
            if status:
                params["status"] = status

            response = await client.get(
                "/api/v1/integrations",
                headers=self._get_headers(token),
                params=params if params else None,
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "Integrations listed",
                    count=data.get("total", len(data.get("items", []))),
                    provider=provider,
                )
                return IntegrationListResponse(**data)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("List integrations request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error listing integrations")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_integration(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> IntegrationDetail:
        """
        Get detailed integration information.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            IntegrationDetail with full configuration

        Raises:
            ResourceNotFoundError: If integration not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/integrations/{integration_id}",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                data = response.json()
                logger.info("Integration retrieved", integration_id=integration_id)
                return IntegrationDetail(**data)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get integration request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error getting integration")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def create_integration(
        self,
        data: IntegrationCreate,
        token: str | None = None,
    ) -> Integration:
        """
        Create a new integration.

        Args:
            data: Integration creation data
            token: Optional JWT token for user authentication

        Returns:
            Created Integration

        Raises:
            ValidationError: If input validation fails
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.post(
                "/api/v1/integrations",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True),
            )

            if response.status_code == 201:
                result = response.json()
                logger.info("Integration created", integration_id=result.get("id"))
                return Integration(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Create integration request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error creating integration")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def update_integration(
        self,
        integration_id: str,
        data: IntegrationUpdate,
        token: str | None = None,
    ) -> Integration:
        """
        Update an integration.

        Args:
            integration_id: Integration ID
            data: Update data
            token: Optional JWT token for user authentication

        Returns:
            Updated Integration

        Raises:
            ResourceNotFoundError: If integration not found
            ValidationError: If input validation fails
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.put(
                f"/api/v1/integrations/{integration_id}",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("Integration updated", integration_id=integration_id)
                return Integration(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Update integration request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error updating integration")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def delete_integration(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> bool:
        """
        Delete (soft delete) an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            True if successfully deleted

        Raises:
            ResourceNotFoundError: If integration not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.delete(
                f"/api/v1/integrations/{integration_id}",
                headers=self._get_headers(token),
            )

            if response.status_code == 204:
                logger.info("Integration deleted", integration_id=integration_id)
                return True
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Delete integration request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        return False

    # =========================================================================
    # Action Execution Method (INT-017 Required)
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def execute_action(
        self,
        integration_id: str,
        action_type: str,
        params: dict[str, Any] | ActionExecuteRequest | None = None,
        token: str | None = None,
    ) -> ActionExecuteResponse:
        """
        Execute an outbound action for an integration.

        Args:
            integration_id: Integration ID
            action_type: Action type (send_message, send_embed, send_blocks, etc.)
            params: Action parameters (content, title, description, etc.)
            token: Optional JWT token for user authentication

        Returns:
            ActionExecuteResponse with result or job_id

        Raises:
            ResourceNotFoundError: If integration or outbound config not found
            ValidationError: If action type or parameters are invalid
            RateLimitError: If rate limit exceeded
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable

        Example:
            ```python
            # Discord send_message
            result = await client.execute_action(
                "integration-id",
                "send_message",
                {"content": "Hello World!"}
            )

            # Discord send_embed
            result = await client.execute_action(
                "integration-id",
                "send_embed",
                {
                    "title": "Status Update",
                    "description": "Everything is running smoothly.",
                    "color": 0x00FF00,
                    "fields": [
                        {"name": "CPU", "value": "45%", "inline": True},
                        {"name": "Memory", "value": "60%", "inline": True},
                    ]
                }
            )

            # Slack send_blocks
            result = await client.execute_action(
                "integration-id",
                "send_blocks",
                {
                    "blocks": [
                        {"type": "header", "text": {"type": "plain_text", "text": "Alert"}}
                    ]
                }
            )

            # Generic webhook POST
            result = await client.execute_action(
                "integration-id",
                "post",
                {"payload": {"key": "value"}}
            )
            ```
        """
        try:
            client = self._get_client()

            # Convert dict to ActionExecuteRequest if needed
            if isinstance(params, dict):
                request_data = params
            elif isinstance(params, ActionExecuteRequest):
                request_data = params.model_dump(exclude_none=True)
            else:
                request_data = {}

            response = await client.post(
                f"/api/v1/integrations/{integration_id}/actions/{action_type}",
                headers=self._get_headers(token),
                json=request_data,
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Action executed",
                    integration_id=integration_id,
                    action_type=action_type,
                    success=result.get("success"),
                )
                return ActionExecuteResponse(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Execute action request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error executing action")

    # =========================================================================
    # Inbound Webhook URL Method (INT-017 Required)
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_inbound_webhook_url(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> str:
        """
        Get the inbound webhook URL for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            Full webhook URL (e.g., https://mimic.fluxtopus.com/api/v1/gateway/integrations/wh-abc123)

        Raises:
            ResourceNotFoundError: If integration or inbound config not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/integrations/{integration_id}/inbound",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                data = response.json()
                webhook_url = data.get("webhook_url", "")
                logger.info(
                    "Inbound webhook URL retrieved",
                    integration_id=integration_id,
                    webhook_url=webhook_url,
                )
                return webhook_url
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get inbound webhook URL request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error getting inbound webhook URL")

    # =========================================================================
    # Credential Management Methods
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def add_credential(
        self,
        integration_id: str,
        data: CredentialCreate,
        token: str | None = None,
    ) -> Credential:
        """
        Add a credential to an integration.

        Args:
            integration_id: Integration ID
            data: Credential creation data
            token: Optional JWT token for user authentication

        Returns:
            Created Credential (without sensitive value)

        Raises:
            ResourceNotFoundError: If integration not found
            ValidationError: If input validation fails
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.post(
                f"/api/v1/integrations/{integration_id}/credentials",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True, mode="json"),
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(
                    "Credential added",
                    integration_id=integration_id,
                    credential_id=result.get("id"),
                )
                return Credential(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Add credential request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error adding credential")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def list_credentials(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> list[Credential]:
        """
        List credentials for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            List of Credential objects (without sensitive values)

        Raises:
            ResourceNotFoundError: If integration not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/integrations/{integration_id}/credentials",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "Credentials listed",
                    integration_id=integration_id,
                    count=len(data),
                )
                return [Credential(**cred) for cred in data]
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("List credentials request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def update_credential(
        self,
        integration_id: str,
        credential_id: str,
        data: CredentialUpdate,
        token: str | None = None,
    ) -> Credential:
        """
        Update a credential.

        Args:
            integration_id: Integration ID
            credential_id: Credential ID
            data: Update data
            token: Optional JWT token for user authentication

        Returns:
            Updated Credential

        Raises:
            ResourceNotFoundError: If integration or credential not found
            ValidationError: If input validation fails
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.put(
                f"/api/v1/integrations/{integration_id}/credentials/{credential_id}",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True, mode="json"),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Credential updated",
                    integration_id=integration_id,
                    credential_id=credential_id,
                )
                return Credential(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Update credential request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error updating credential")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def delete_credential(
        self,
        integration_id: str,
        credential_id: str,
        token: str | None = None,
    ) -> bool:
        """
        Delete a credential.

        Args:
            integration_id: Integration ID
            credential_id: Credential ID
            token: Optional JWT token for user authentication

        Returns:
            True if successfully deleted

        Raises:
            ResourceNotFoundError: If integration or credential not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.delete(
                f"/api/v1/integrations/{integration_id}/credentials/{credential_id}",
                headers=self._get_headers(token),
            )

            if response.status_code == 204:
                logger.info(
                    "Credential deleted",
                    integration_id=integration_id,
                    credential_id=credential_id,
                )
                return True
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Delete credential request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def test_credential(
        self,
        integration_id: str,
        credential_id: str,
        token: str | None = None,
    ) -> CredentialTestResult:
        """
        Test a credential by validating it against the external service.

        Args:
            integration_id: Integration ID
            credential_id: Credential ID
            token: Optional JWT token for user authentication

        Returns:
            CredentialTestResult with success status and message

        Raises:
            ResourceNotFoundError: If integration or credential not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.post(
                f"/api/v1/integrations/{integration_id}/credentials/{credential_id}/test",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Credential tested",
                    integration_id=integration_id,
                    credential_id=credential_id,
                    success=result.get("success"),
                )
                return CredentialTestResult(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Test credential request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error testing credential")

    # =========================================================================
    # Inbound Config Management Methods
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def set_inbound_config(
        self,
        integration_id: str,
        data: InboundConfigCreate,
        token: str | None = None,
    ) -> InboundConfig:
        """
        Set inbound webhook configuration for an integration.

        Args:
            integration_id: Integration ID
            data: Inbound config data
            token: Optional JWT token for user authentication

        Returns:
            InboundConfig with full webhook URL

        Raises:
            ResourceNotFoundError: If integration not found
            ValidationError: If input validation fails or direction is outbound-only
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.put(
                f"/api/v1/integrations/{integration_id}/inbound",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Inbound config set",
                    integration_id=integration_id,
                    webhook_path=result.get("webhook_path"),
                )
                return InboundConfig(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Set inbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error setting inbound config")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_inbound_config(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> InboundConfig:
        """
        Get inbound webhook configuration for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            InboundConfig

        Raises:
            ResourceNotFoundError: If integration or inbound config not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/integrations/{integration_id}/inbound",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("Inbound config retrieved", integration_id=integration_id)
                return InboundConfig(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get inbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error getting inbound config")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def delete_inbound_config(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> bool:
        """
        Delete inbound webhook configuration for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            True if successfully deleted

        Raises:
            ResourceNotFoundError: If integration or inbound config not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.delete(
                f"/api/v1/integrations/{integration_id}/inbound",
                headers=self._get_headers(token),
            )

            if response.status_code == 204:
                logger.info("Inbound config deleted", integration_id=integration_id)
                return True
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Delete inbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        return False

    # =========================================================================
    # Outbound Config Management Methods
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def set_outbound_config(
        self,
        integration_id: str,
        data: OutboundConfigCreate,
        token: str | None = None,
    ) -> OutboundConfig:
        """
        Set outbound action configuration for an integration.

        Args:
            integration_id: Integration ID
            data: Outbound config data
            token: Optional JWT token for user authentication

        Returns:
            OutboundConfig

        Raises:
            ResourceNotFoundError: If integration not found
            ValidationError: If action type not supported or direction is inbound-only
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.put(
                f"/api/v1/integrations/{integration_id}/outbound",
                headers=self._get_headers(token),
                json=data.model_dump(exclude_none=True),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Outbound config set",
                    integration_id=integration_id,
                    action_type=result.get("action_type"),
                )
                return OutboundConfig(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Set outbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error setting outbound config")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_outbound_config(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> OutboundConfig:
        """
        Get outbound action configuration for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            OutboundConfig

        Raises:
            ResourceNotFoundError: If integration or outbound config not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/integrations/{integration_id}/outbound",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("Outbound config retrieved", integration_id=integration_id)
                return OutboundConfig(**result)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get outbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        raise MimicError("Unexpected error getting outbound config")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def delete_outbound_config(
        self,
        integration_id: str,
        token: str | None = None,
    ) -> bool:
        """
        Delete outbound action configuration for an integration.

        Args:
            integration_id: Integration ID
            token: Optional JWT token for user authentication

        Returns:
            True if successfully deleted

        Raises:
            ResourceNotFoundError: If integration or outbound config not found
            AuthenticationError: If authentication fails
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.delete(
                f"/api/v1/integrations/{integration_id}/outbound",
                headers=self._get_headers(token),
            )

            if response.status_code == 204:
                logger.info("Outbound config deleted", integration_id=integration_id)
                return True
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Delete outbound config request failed", error=str(e))
            raise ServiceUnavailableError(f"Mimic service unavailable: {e}")

        return False
