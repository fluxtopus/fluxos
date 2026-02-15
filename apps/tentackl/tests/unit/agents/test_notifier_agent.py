"""Unit tests for NotifierAgent"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.notifier import NotifierAgent
from src.agents.base import AgentConfig, AgentStatus
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult


@pytest.fixture
def agent_config():
    """Create agent config for testing"""
    return AgentConfig(
        name="test-notifier",
        agent_type="notifier",
        timeout=60
    )


@pytest.fixture
def notifier_agent(agent_config):
    """Create NotifierAgent instance"""
    agent = NotifierAgent(agent_config)
    return agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notifier_agent_execute_success(notifier_agent):
    """Test successful notification execution"""
    mock_result = NotificationResult(
        success=True,
        provider="email",
        message_id="msg-123"
    )

    with patch.object(notifier_agent, '_get_provider') as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.send = AsyncMock(return_value=mock_result)
        mock_get_provider.return_value = mock_provider

        task = {
            "provider": "email",
            "recipient": "user@example.com",
            "content": "Test message",
            "provider_credentials": {
                "api_key": "test-key",
                "from_email": "sender@example.com"
            }
        }

        result = await notifier_agent.execute(task)

        assert result["success"] is True
        assert result["provider"] == "email"
        mock_provider.send.assert_called_once_with(
            recipient="user@example.com",
            content="Test message"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notifier_agent_execute_failure(notifier_agent):
    """Test notification execution failure"""
    mock_result = NotificationResult(
        success=False,
        provider="email",
        error="Test error"
    )

    with patch.object(notifier_agent, '_get_provider') as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.send = AsyncMock(return_value=mock_result)
        mock_get_provider.return_value = mock_provider

        task = {
            "provider": "email",
            "recipient": "user@example.com",
            "content": "Test message",
            "provider_credentials": {
                "api_key": "test-key",
                "from_email": "sender@example.com"
            }
        }

        with pytest.raises(RuntimeError, match="Failed to send notification"):
            await notifier_agent.execute(task)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notifier_agent_missing_provider(notifier_agent):
    """Test execution with unknown provider type"""
    task = {
        "provider": "nonexistent",
        "recipient": "user@example.com",
        "content": "Test message",
        "provider_credentials": {}
    }

    with pytest.raises(ValueError, match="Unknown provider type: nonexistent"):
        await notifier_agent.execute(task)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notifier_agent_missing_fields(notifier_agent):
    """Test execution with missing required fields"""
    # Missing recipient
    task = {
        "provider": "email",
        "content": "Test message",
        "provider_credentials": {}
    }

    with pytest.raises(ValueError, match="Missing required fields"):
        await notifier_agent.execute(task)

    # Missing content
    task = {
        "provider": "email",
        "recipient": "user@example.com",
        "provider_credentials": {}
    }

    with pytest.raises(ValueError, match="Missing required fields"):
        await notifier_agent.execute(task)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notifier_agent_with_metadata(notifier_agent):
    """Test execution with metadata passed to provider"""
    mock_result = NotificationResult(
        success=True,
        provider="email",
        message_id="msg-123"
    )

    with patch.object(notifier_agent, '_get_provider') as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.send = AsyncMock(return_value=mock_result)
        mock_get_provider.return_value = mock_provider

        task = {
            "provider": "email",
            "recipient": "user@example.com",
            "content": "Test message",
            "provider_credentials": {
                "api_key": "test-key",
                "from_email": "sender@example.com"
            },
            "metadata": {
                "subject": "Test Subject",
                "html_content": "<p>HTML content</p>"
            }
        }

        result = await notifier_agent.execute(task)

        assert result["success"] is True
        # Verify metadata was passed as kwargs
        mock_provider.send.assert_called_once_with(
            recipient="user@example.com",
            content="Test message",
            subject="Test Subject",
            html_content="<p>HTML content</p>"
        )


@pytest.mark.unit
def test_notifier_agent_get_provider_email_raises(notifier_agent):
    """Test _get_provider raises for email (handled by send_email plugin)"""
    credentials = {"api_key": "test-key", "from_email": "test@example.com"}

    with pytest.raises(ValueError, match="send_email plugin"):
        notifier_agent._get_provider("email", credentials)


@pytest.mark.unit
def test_notifier_agent_get_provider_unknown(notifier_agent):
    """Test _get_provider raises for unknown provider"""
    with pytest.raises(ValueError, match="Unknown provider type"):
        notifier_agent._get_provider("unknown_provider", {})
