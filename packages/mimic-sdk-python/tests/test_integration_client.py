"""Unit tests for Mimic Integration Client (INT-017)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from mimic import (
    MimicIntegrationClient,
    MimicConfig,
    MimicError,
    AuthenticationError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
    RateLimitError,
    ServiceUnavailableError,
    IntegrationCreate,
    IntegrationUpdate,
    CredentialCreate,
    CredentialUpdate,
    InboundConfigCreate,
    OutboundConfigCreate,
    IntegrationProvider,
    IntegrationDirection,
    CredentialType,
    InboundAuthMethod,
    DestinationService,
    OutboundActionType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config():
    """Create a test configuration."""
    return MimicConfig(
        base_url="http://test-mimic:8000",
        api_key="test-api-key",
        timeout=5.0,
    )


@pytest.fixture
def client(config):
    """Create a test client."""
    return MimicIntegrationClient(config)


@pytest.fixture
def mock_integration_response():
    """Mock integration response data."""
    return {
        "id": "int-123",
        "organization_id": "org-456",
        "user_id": "user-789",
        "name": "Test Discord Integration",
        "provider": "discord",
        "direction": "bidirectional",
        "status": "active",
        "created_at": "2026-01-25T12:00:00Z",
        "updated_at": "2026-01-25T12:00:00Z",
    }


@pytest.fixture
def mock_integration_detail_response(mock_integration_response):
    """Mock integration detail response data."""
    return {
        **mock_integration_response,
        "credentials": [
            {
                "id": "cred-123",
                "credential_type": "webhook_url",
                "has_expiration": False,
                "is_expired": False,
                "created_at": "2026-01-25T12:00:00Z",
            }
        ],
        "inbound_config": {
            "webhook_path": "wh-test-path",
            "webhook_url": "https://mimic.fluxtopus.com/api/v1/gateway/integrations/wh-test-path",
            "auth_method": "signature",
            "destination_service": "tentackl",
            "is_active": True,
        },
        "outbound_config": {
            "action_type": "send_message",
            "has_rate_limit": True,
            "is_active": True,
        },
    }


# =============================================================================
# Config Tests
# =============================================================================


class TestMimicConfig:
    """Tests for MimicConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MimicConfig()
        assert config.base_url == "http://localhost:8006"
        assert config.api_key is None
        assert config.timeout == 5.0
        assert config.max_retries == 3
        assert config.verify_ssl is True

    def test_config_with_values(self):
        """Test configuration with custom values."""
        config = MimicConfig(
            base_url="http://custom:9000",
            api_key="custom-key",
            timeout=10.0,
            max_retries=5,
        )
        assert config.base_url == "http://custom:9000"
        assert config.api_key == "custom-key"
        assert config.timeout == 10.0
        assert config.max_retries == 5

    def test_config_removes_trailing_slash(self):
        """Test that trailing slash is removed from base_url."""
        config = MimicConfig(base_url="http://test:8000/")
        assert config.base_url == "http://test:8000"

    def test_config_validates_timeout(self):
        """Test that invalid timeout raises error."""
        with pytest.raises(ValueError, match="timeout must be greater than 0"):
            MimicConfig(timeout=0)

    def test_config_validates_max_retries(self):
        """Test that invalid max_retries raises error."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            MimicConfig(max_retries=-1)


# =============================================================================
# Client Initialization Tests
# =============================================================================


class TestMimicIntegrationClientInit:
    """Tests for MimicIntegrationClient initialization."""

    def test_init_with_config(self, config):
        """Test client initialization with config."""
        client = MimicIntegrationClient(config)
        assert client.config == config
        assert client._client is None

    def test_init_without_config(self):
        """Test client initialization without config uses defaults."""
        client = MimicIntegrationClient()
        assert client.config.base_url == "http://localhost:8006"

    def test_get_headers_with_api_key(self, client):
        """Test _get_headers returns API key header."""
        headers = client._get_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["X-API-Key"] == "test-api-key"

    def test_get_headers_with_token(self, client):
        """Test _get_headers with token overrides API key."""
        headers = client._get_headers(token="bearer-token")
        assert headers["Authorization"] == "Bearer bearer-token"
        assert "X-API-Key" not in headers


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_handle_400_error(self, client):
        """Test handling 400 Bad Request."""
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {"detail": "Invalid input"}
        response.text = "Invalid input"

        with pytest.raises(ValidationError) as exc_info:
            client._handle_error(response)
        assert "Invalid input" in str(exc_info.value)

    def test_handle_401_error(self, client):
        """Test handling 401 Unauthorized."""
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"detail": "Invalid token"}
        response.text = "Invalid token"

        with pytest.raises(AuthenticationError) as exc_info:
            client._handle_error(response)
        assert exc_info.value.status_code == 401

    def test_handle_403_error(self, client):
        """Test handling 403 Forbidden."""
        response = MagicMock()
        response.status_code = 403
        response.json.return_value = {"detail": "Permission denied"}
        response.text = "Permission denied"

        with pytest.raises(PermissionDeniedError):
            client._handle_error(response)

    def test_handle_404_error(self, client):
        """Test handling 404 Not Found."""
        response = MagicMock()
        response.status_code = 404
        response.json.return_value = {"detail": "Integration not found"}
        response.text = "Integration not found"

        with pytest.raises(ResourceNotFoundError):
            client._handle_error(response)

    def test_handle_429_error(self, client):
        """Test handling 429 Rate Limit."""
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {
            "detail": "Rate limit exceeded",
            "retry_after_seconds": 30,
        }
        response.text = "Rate limit exceeded"

        with pytest.raises(RateLimitError) as exc_info:
            client._handle_error(response)
        assert exc_info.value.retry_after_seconds == 30

    def test_handle_503_error(self, client):
        """Test handling 503 Service Unavailable."""
        response = MagicMock()
        response.status_code = 503
        response.json.return_value = {"detail": "Service unavailable"}
        response.text = "Service unavailable"

        with pytest.raises(ServiceUnavailableError):
            client._handle_error(response)


# =============================================================================
# List Integrations Tests
# =============================================================================


class TestListIntegrations:
    """Tests for list_integrations method."""

    @pytest.mark.asyncio
    async def test_list_integrations_success(self, client, mock_integration_response):
        """Test successful list integrations."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [mock_integration_response],
            "total": 1,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.list_integrations()

            assert result.total == 1
            assert len(result.items) == 1
            assert result.items[0].id == "int-123"
            assert result.items[0].provider == "discord"

    @pytest.mark.asyncio
    async def test_list_integrations_with_provider_filter(self, client):
        """Test list integrations with provider filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [], "total": 0}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            await client.list_integrations(provider="discord")

            # Verify params were passed
            call_kwargs = mock_http_client.get.call_args
            assert call_kwargs[1]["params"] == {"provider": "discord"}

    @pytest.mark.asyncio
    async def test_list_integrations_auth_failure(self, client):
        """Test list integrations with auth failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid API key"}
        mock_response.text = "Invalid API key"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(AuthenticationError):
                await client.list_integrations()


# =============================================================================
# Get Integration Tests
# =============================================================================


class TestGetIntegration:
    """Tests for get_integration method."""

    @pytest.mark.asyncio
    async def test_get_integration_success(self, client, mock_integration_detail_response):
        """Test successful get integration."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_integration_detail_response

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_integration("int-123")

            assert result.id == "int-123"
            assert result.name == "Test Discord Integration"
            assert len(result.credentials) == 1
            assert result.inbound_config is not None
            assert result.inbound_config.webhook_path == "wh-test-path"
            assert result.outbound_config is not None

    @pytest.mark.asyncio
    async def test_get_integration_not_found(self, client):
        """Test get integration returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Integration not found"}
        mock_response.text = "Integration not found"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(ResourceNotFoundError):
                await client.get_integration("int-nonexistent")


# =============================================================================
# Execute Action Tests (INT-017 Required)
# =============================================================================


class TestExecuteAction:
    """Tests for execute_action method (INT-017 required)."""

    @pytest.mark.asyncio
    async def test_execute_action_success(self, client):
        """Test successful action execution."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "integration_id": "int-123",
            "action_type": "send_message",
            "result": {"message_id": "msg-456"},
            "job_id": None,
            "message": "Action executed successfully",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.execute_action(
                "int-123",
                "send_message",
                {"content": "Hello World!"},
            )

            assert result.success is True
            assert result.integration_id == "int-123"
            assert result.action_type == "send_message"
            assert result.result["message_id"] == "msg-456"

    @pytest.mark.asyncio
    async def test_execute_action_with_discord_embed(self, client):
        """Test action execution with Discord embed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "integration_id": "int-123",
            "action_type": "send_embed",
            "result": {"message_id": "msg-789"},
            "job_id": None,
            "message": "Action executed successfully",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.execute_action(
                "int-123",
                "send_embed",
                {
                    "title": "Status Update",
                    "description": "All systems operational",
                    "color": 0x00FF00,
                    "fields": [
                        {"name": "CPU", "value": "45%", "inline": True},
                    ],
                },
            )

            assert result.success is True
            assert result.action_type == "send_embed"

    @pytest.mark.asyncio
    async def test_execute_action_async_mode(self, client):
        """Test async action execution returns job_id."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "integration_id": "int-123",
            "action_type": "send_message",
            "result": None,
            "job_id": "celery-task-id-123",
            "message": "Action queued for execution",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.execute_action(
                "int-123",
                "send_message",
                {"content": "Hello!", "async_execution": True},
            )

            assert result.job_id == "celery-task-id-123"
            assert result.result is None

    @pytest.mark.asyncio
    async def test_execute_action_rate_limited(self, client):
        """Test action execution returns 429 rate limit."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "error": "RateLimitExceeded",
            "message": "Rate limit exceeded",
            "retry_after_seconds": 60,
        }
        mock_response.text = "Rate limit exceeded"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(RateLimitError) as exc_info:
                await client.execute_action(
                    "int-123",
                    "send_message",
                    {"content": "Hello!"},
                )
            assert exc_info.value.retry_after_seconds == 60

    @pytest.mark.asyncio
    async def test_execute_action_validation_error(self, client):
        """Test action execution with invalid action type."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "detail": "Invalid action_type: invalid_action"
        }
        mock_response.text = "Invalid action_type"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(ValidationError):
                await client.execute_action(
                    "int-123",
                    "invalid_action",
                    {},
                )


# =============================================================================
# Get Inbound Webhook URL Tests (INT-017 Required)
# =============================================================================


class TestGetInboundWebhookUrl:
    """Tests for get_inbound_webhook_url method (INT-017 required)."""

    @pytest.mark.asyncio
    async def test_get_inbound_webhook_url_success(self, client):
        """Test successful get inbound webhook URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "config-123",
            "integration_id": "int-123",
            "webhook_path": "wh-abc123",
            "webhook_url": "https://mimic.fluxtopus.com/api/v1/gateway/integrations/wh-abc123",
            "auth_method": "signature",
            "has_signature_secret": True,
            "event_filters": None,
            "transform_template": None,
            "destination_service": "tentackl",
            "destination_config": {"task_template_id": "tpl-123"},
            "is_active": True,
            "created_at": "2026-01-25T12:00:00Z",
            "updated_at": "2026-01-25T12:00:00Z",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.get_inbound_webhook_url("int-123")

            assert result == "https://mimic.fluxtopus.com/api/v1/gateway/integrations/wh-abc123"

    @pytest.mark.asyncio
    async def test_get_inbound_webhook_url_not_found(self, client):
        """Test get inbound webhook URL when config not found."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Inbound config not found"}
        mock_response.text = "Inbound config not found"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            with pytest.raises(ResourceNotFoundError):
                await client.get_inbound_webhook_url("int-nonexistent")


# =============================================================================
# Credential Management Tests
# =============================================================================


class TestCredentialManagement:
    """Tests for credential management methods."""

    @pytest.mark.asyncio
    async def test_add_credential_success(self, client):
        """Test successful add credential."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "cred-123",
            "credential_type": "webhook_url",
            "has_value": True,
            "metadata": {"channel_id": "123"},
            "has_expiration": False,
            "is_expired": False,
            "created_at": "2026-01-25T12:00:00Z",
            "updated_at": "2026-01-25T12:00:00Z",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.add_credential(
                "int-123",
                CredentialCreate(
                    credential_type=CredentialType.webhook_url,
                    value="https://discord.com/api/webhooks/...",
                    metadata={"channel_id": "123"},
                ),
            )

            assert result.id == "cred-123"
            assert result.credential_type == "webhook_url"
            assert result.has_value is True

    @pytest.mark.asyncio
    async def test_add_credential_with_credential_metadata_alias(self, client):
        """Test add credential using credential_metadata alias."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "cred-789",
            "credential_type": "webhook_url",
            "has_value": True,
            "metadata": {"channel_id": "456"},
            "has_expiration": False,
            "is_expired": False,
            "created_at": "2026-01-25T12:00:00Z",
            "updated_at": "2026-01-25T12:00:00Z",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            # Use credential_metadata instead of metadata
            result = await client.add_credential(
                "int-123",
                CredentialCreate(
                    credential_type=CredentialType.webhook_url,
                    value="https://discord.com/api/webhooks/...",
                    credential_metadata={"channel_id": "456"},
                ),
            )

            assert result.id == "cred-789"
            assert result.metadata == {"channel_id": "456"}

    @pytest.mark.asyncio
    async def test_list_credentials_success(self, client):
        """Test successful list credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "cred-123",
                "credential_type": "webhook_url",
                "has_value": True,
                "metadata": {},
                "has_expiration": False,
                "is_expired": False,
                "created_at": "2026-01-25T12:00:00Z",
                "updated_at": "2026-01-25T12:00:00Z",
            },
            {
                "id": "cred-456",
                "credential_type": "api_key",
                "has_value": True,
                "metadata": {},
                "has_expiration": True,
                "is_expired": False,
                "created_at": "2026-01-25T12:00:00Z",
                "updated_at": "2026-01-25T12:00:00Z",
            },
        ]

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.list_credentials("int-123")

            assert len(result) == 2
            assert result[0].id == "cred-123"
            assert result[1].credential_type == "api_key"

    @pytest.mark.asyncio
    async def test_test_credential_success(self, client):
        """Test successful credential test."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Webhook URL is valid",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.test_credential("int-123", "cred-123")

            assert result.success is True
            assert "valid" in result.message.lower()


# =============================================================================
# Inbound Config Management Tests
# =============================================================================


class TestInboundConfigManagement:
    """Tests for inbound config management methods."""

    @pytest.mark.asyncio
    async def test_set_inbound_config_success(self, client):
        """Test successful set inbound config."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "config-123",
            "integration_id": "int-123",
            "webhook_path": "wh-custom-path",
            "webhook_url": "https://mimic.fluxtopus.com/api/v1/gateway/integrations/wh-custom-path",
            "auth_method": "signature",
            "has_signature_secret": True,
            "event_filters": ["push", "pull_request"],
            "transform_template": '{"event": "{{ event_type }}"}',
            "destination_service": "tentackl",
            "destination_config": {"task_template_id": "tpl-123"},
            "is_active": True,
            "created_at": "2026-01-25T12:00:00Z",
            "updated_at": "2026-01-25T12:00:00Z",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.put.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.set_inbound_config(
                "int-123",
                InboundConfigCreate(
                    webhook_path="wh-custom-path",
                    auth_method=InboundAuthMethod.signature,
                    signature_secret="my-secret",
                    event_filters=["push", "pull_request"],
                    destination_service=DestinationService.tentackl,
                    destination_config={"task_template_id": "tpl-123"},
                ),
            )

            assert result.webhook_path == "wh-custom-path"
            assert result.auth_method == "signature"
            assert result.has_signature_secret is True


# =============================================================================
# Outbound Config Management Tests
# =============================================================================


class TestOutboundConfigManagement:
    """Tests for outbound config management methods."""

    @pytest.mark.asyncio
    async def test_set_outbound_config_success(self, client):
        """Test successful set outbound config."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "config-456",
            "integration_id": "int-123",
            "action_type": "send_message",
            "default_template": {"username": "Mimic Bot"},
            "rate_limit_requests": 100,
            "rate_limit_window_seconds": 60,
            "is_active": True,
            "created_at": "2026-01-25T12:00:00Z",
            "updated_at": "2026-01-25T12:00:00Z",
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.put.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            result = await client.set_outbound_config(
                "int-123",
                OutboundConfigCreate(
                    action_type=OutboundActionType.send_message,
                    default_template={"username": "Mimic Bot"},
                    rate_limit_requests=100,
                    rate_limit_window_seconds=60,
                ),
            )

            assert result.action_type == "send_message"
            assert result.rate_limit_requests == 100
            assert result.rate_limit_window_seconds == 60


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_client(self, config):
        """Test that context manager creates HTTP client."""
        async with MimicIntegrationClient(config) as client:
            assert client._client is not None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self, config):
        """Test that context manager closes HTTP client on exit."""
        async with MimicIntegrationClient(config) as client:
            pass
        # Client should be closed after exiting context
        assert client._client is None


# =============================================================================
# Service Unavailable Tests
# =============================================================================


class TestServiceUnavailable:
    """Tests for service unavailable scenarios."""

    @pytest.mark.asyncio
    async def test_list_integrations_service_unavailable(self, client):
        """Test list integrations when service is unavailable."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.side_effect = httpx.RequestError("Connection refused")
            mock_get_client.return_value = mock_http_client

            with pytest.raises(ServiceUnavailableError):
                await client.list_integrations()

    @pytest.mark.asyncio
    async def test_execute_action_service_unavailable(self, client):
        """Test execute action when service is unavailable."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.side_effect = httpx.RequestError("Connection refused")
            mock_get_client.return_value = mock_http_client

            with pytest.raises(ServiceUnavailableError):
                await client.execute_action(
                    "int-123",
                    "send_message",
                    {"content": "Hello!"},
                )
