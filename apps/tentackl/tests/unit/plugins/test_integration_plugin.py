"""Unit tests for integration plugin (INT-018 Mimic migration).

Tests the integration plugins that proxy to Mimic for:
- Creating integrations
- Configuring inbound webhooks
- Executing outbound actions
- Linking webhooks to templates
- Getting integration status
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.plugins.integration_plugin import (
    create_integration_handler,
    configure_inbound_webhook_handler,
    execute_outbound_action_handler,
    link_webhook_to_template_handler,
    get_integration_status_handler,
    INTEGRATION_PLUGIN_DEFINITIONS,
)


class TestPluginDefinitions:
    """Tests for plugin definition structure."""

    def test_all_plugins_have_required_fields(self):
        """All plugins should have name, description, handler, schemas."""
        required_fields = ["name", "description", "handler", "inputs_schema", "outputs_schema"]

        for plugin in INTEGRATION_PLUGIN_DEFINITIONS:
            for field in required_fields:
                assert field in plugin, f"Plugin {plugin.get('name', 'unknown')} missing {field}"

    def test_create_integration_plugin_schema(self):
        """create_integration should require name and user_token."""
        plugin = next(p for p in INTEGRATION_PLUGIN_DEFINITIONS if p["name"] == "create_integration")

        required = plugin["inputs_schema"].get("required", [])
        assert "name" in required
        assert "user_token" in required

    def test_execute_outbound_action_plugin_schema(self):
        """execute_outbound_action should require integration_id, action_type, user_token."""
        plugin = next(p for p in INTEGRATION_PLUGIN_DEFINITIONS if p["name"] == "execute_outbound_action")

        required = plugin["inputs_schema"].get("required", [])
        assert "integration_id" in required
        assert "action_type" in required
        assert "user_token" in required


@pytest.mark.asyncio
class TestCreateIntegrationHandler:
    """Tests for create_integration_handler."""

    async def test_missing_name(self):
        """Should return error when name is missing."""
        result = await create_integration_handler({
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "name is required" in result["error"]

    async def test_missing_token(self):
        """Should return error when user_token is missing."""
        result = await create_integration_handler({
            "name": "test-integration",
        })

        assert result["success"] is False
        assert "user_token is required" in result["error"]

    async def test_invalid_provider(self):
        """Should return error for invalid provider enum."""
        result = await create_integration_handler({
            "name": "test-integration",
            "provider": "invalid_provider",
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "Invalid provider or direction" in result["error"]


@pytest.mark.asyncio
class TestConfigureInboundWebhookHandler:
    """Tests for configure_inbound_webhook_handler."""

    async def test_missing_integration_id(self):
        """Should return error when integration_id is missing."""
        result = await configure_inbound_webhook_handler({
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "integration_id is required" in result["error"]

    async def test_missing_token(self):
        """Should return error when user_token is missing."""
        result = await configure_inbound_webhook_handler({
            "integration_id": "int-123",
        })

        assert result["success"] is False
        assert "user_token is required" in result["error"]

    async def test_invalid_auth_method(self):
        """Should return error for invalid auth method."""
        result = await configure_inbound_webhook_handler({
            "integration_id": "int-123",
            "auth_method": "invalid_auth",
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "Invalid auth_method" in result["error"]


@pytest.mark.asyncio
class TestExecuteOutboundActionHandler:
    """Tests for execute_outbound_action_handler."""

    async def test_missing_integration_id(self):
        """Should return error when integration_id is missing."""
        result = await execute_outbound_action_handler({
            "action_type": "send_message",
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "integration_id is required" in result["error"]

    async def test_missing_token(self):
        """Should return error when user_token is missing."""
        result = await execute_outbound_action_handler({
            "integration_id": "int-123",
            "action_type": "send_message",
        })

        assert result["success"] is False
        assert "user_token is required" in result["error"]


@pytest.mark.asyncio
class TestLinkWebhookToTemplateHandler:
    """Tests for link_webhook_to_template_handler."""

    async def test_missing_template_id(self):
        """Should return error when template_id is missing."""
        result = await link_webhook_to_template_handler({
            "integration_id": "int-123",
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "template_id is required" in result["error"]

    async def test_missing_integration_id(self):
        """Should return error when integration_id is missing."""
        result = await link_webhook_to_template_handler({
            "template_id": "tpl-456",
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "integration_id is required" in result["error"]

    async def test_missing_token(self):
        """Should return error when user_token is missing."""
        result = await link_webhook_to_template_handler({
            "integration_id": "int-123",
            "template_id": "tpl-456",
        })

        assert result["success"] is False
        assert "user_token is required" in result["error"]


@pytest.mark.asyncio
class TestGetIntegrationStatusHandler:
    """Tests for get_integration_status_handler."""

    async def test_missing_integration_id(self):
        """Should return error when integration_id is missing."""
        result = await get_integration_status_handler({
            "user_token": "test-token",
        })

        assert result["success"] is False
        assert "integration_id is required" in result["error"]

    async def test_missing_token(self):
        """Should return error when user_token is missing."""
        result = await get_integration_status_handler({
            "integration_id": "int-123",
        })

        assert result["success"] is False
        assert "user_token is required" in result["error"]
