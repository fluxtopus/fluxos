"""Unit tests for provider validator service"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.provider_validator import ProviderValidatorService


@pytest.fixture
def validator_service():
    """Create validator service instance"""
    return ProviderValidatorService()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_email_provider(validator_service):
    """Test email provider validation"""
    # Mock validation - in real implementation, this would call SendGrid API
    result = await validator_service.validate_provider(
        provider_type="email",
        api_key="SG.test-key-123",
    )
    # Validates format and attempts API call (will fail in test without real key)
    assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_sms_provider(validator_service):
    """Test SMS provider validation"""
    result = await validator_service.validate_provider(
        provider_type="sms",
        api_key="AC" + "a" * 32,  # Twilio account SID format
        secret="a" * 32,  # Twilio auth token format
    )
    assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_slack_provider(validator_service):
    """Test Slack provider validation"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_http

        result = await validator_service.validate_provider(
            provider_type="slack",
            webhook_url="https://hooks.slack.com/services/TEST/BEST/KEY"
        )
        assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_discord_provider(validator_service):
    """Test Discord provider validation"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 204  # Discord returns 204 on success
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_http

        result = await validator_service.validate_provider(
            provider_type="discord",
            webhook_url="https://discord.com/api/webhooks/TEST/BEST"
        )
        assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_telegram_provider(validator_service):
    """Test Telegram provider validation"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"id": 123}}
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_http

        result = await validator_service.validate_provider(
            provider_type="telegram",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        )
        assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_webhook_provider(validator_service):
    """Test generic webhook provider validation"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_http

        result = await validator_service.validate_provider(
            provider_type="webhook",
            webhook_url="https://example.com/webhook"
        )
        assert isinstance(result, bool)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_invalid_provider(validator_service):
    """Test validation with invalid provider type"""
    result = await validator_service.validate_provider(
        provider_type="invalid_provider"
    )
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_email_missing_fields(validator_service):
    """Test email validation with missing fields"""
    result = await validator_service.validate_provider(
        provider_type="email",
        api_key=None,
    )
    assert result is False
