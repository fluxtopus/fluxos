"""Unit tests for SlackProvider"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.providers.slack_provider import SlackProvider
from src.interfaces.notification_provider import NotificationResult


@pytest.fixture
def slack_provider():
    """Create SlackProvider instance"""
    return SlackProvider(credentials={"webhook_url": "https://hooks.slack.com/services/TEST/BEST/KEY"})


@pytest.mark.asyncio
async def test_slack_provider_send_success(slack_provider):
    """Test successful Slack message send"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance

        result = await slack_provider.send(
            recipient="#general",
            content="Test Slack message"
        )

        assert result.success is True
        assert result.provider == "slack"


@pytest.mark.asyncio
async def test_slack_provider_send_failure(slack_provider):
    """Test Slack send failure"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_payload"

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance

        result = await slack_provider.send(
            recipient="#general",
            content="Test message"
        )

        assert result.success is False
        assert result.provider == "slack"


def test_slack_provider_validate_config():
    """Test Slack provider config validation"""
    provider = SlackProvider(credentials={"webhook_url": "https://hooks.slack.com/services/TEST/BEST/KEY"})

    valid_config = {"webhook_url": "https://hooks.slack.com/services/TEST/BEST/KEY"}
    assert provider.validate_config(valid_config) is True

    invalid_config = {}
    assert provider.validate_config(invalid_config) is False


def test_slack_provider_missing_webhook():
    """Test SlackProvider raises error when webhook_url is missing"""
    with pytest.raises(ValueError, match="requires 'webhook_url'"):
        SlackProvider(credentials={})
