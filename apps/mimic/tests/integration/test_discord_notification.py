"""Integration test for Discord notification delivery"""

import pytest
import httpx
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.api.routes.auth import hash_api_key
from src.services.key_encryption import KeyEncryptionService
from src.database.models import User, APIKey, ProviderKey, DeliveryLog
from datetime import datetime
import subprocess
import time
import os


@pytest.fixture(scope="module")
def mock_discord_server():
    """Start mock Discord server"""
    import sys
    server_path = os.path.join(os.path.dirname(__file__), "..", "mock_servers", "discord_mock_server.py")
    
    # Start server in background
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.mock_servers.discord_mock_server:app", "--port", "8080"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(2)
    
    yield process
    
    # Cleanup
    process.terminate()
    process.wait()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires running InkPass service and mock Discord server")
async def test_discord_notification_delivery(client, test_user_annual, db_session, mock_discord_server):
    """Test sending a Discord notification through the full stack"""
    from src.database.models import APIKey, ProviderKey
    
    # 1. Create API key for user
    api_key_value = "test-discord-api-key"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Discord Test API Key",
    )
    db_session.add(api_key)
    
    # 2. Create Discord provider key with mock webhook URL
    encryption_service = KeyEncryptionService()
    # Discord uses webhook URL, no encryption needed for URL
    webhook_url = "http://localhost:8080/webhooks/test_webhook_id/test_webhook_token"
    
    provider_key = ProviderKey(
        user_id=test_user_annual.id,
        provider_type="discord",
        webhook_url=webhook_url,
        is_active=True
    )
    db_session.add(provider_key)
    db_session.commit()
    
    # 3. Mock Tentackl client to return workflow ID
    with patch('src.clients.tentackl_client.TentacklClient.send_notification') as mock_send:
        mock_send.return_value = "workflow-run-123"
        
        # 4. Send notification via API
        response = client.post(
            "/api/v1/send",
            json={
                "recipient": "#general",
                "content": "Test Discord notification from Mimic!",
                "provider": "discord"
            },
            headers={"Authorization": f"Bearer {api_key_value}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "delivery_id" in data
        delivery_id = data["delivery_id"]
    
    # 5. Wait a bit for async processing
    await asyncio.sleep(1)
    
    # 6. Verify message was received by mock server
    async with httpx.AsyncClient() as http_client:
        messages_response = await http_client.get("http://localhost:8080/messages")
        assert messages_response.status_code == 200
        messages_data = messages_response.json()
        
        assert messages_data["count"] > 0
        assert len(messages_data["messages"]) > 0
        
        # Check the last message
        last_message = messages_data["messages"][-1]
        assert "payload" in last_message
        payload = last_message["payload"]
        
        # Discord webhook payload should contain content
        assert "content" in payload
        assert payload["content"] == "Test Discord notification from Mimic!"
    
    # 7. Verify delivery log was created
    delivery_log = db_session.query(DeliveryLog).filter(
        DeliveryLog.delivery_id == delivery_id
    ).first()
    
    assert delivery_log is not None
    assert delivery_log.provider == "discord"
    assert delivery_log.recipient == "#general"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="src.agents.providers.discord_provider does not exist in Mimic")
async def test_discord_provider_direct(mock_discord_server):
    """Test Discord provider directly (unit test style)"""
    from src.agents.providers.discord_provider import DiscordProvider
    
    webhook_url = "http://localhost:8080/webhooks/test_id/test_token"
    provider = DiscordProvider(webhook_url=webhook_url)
    
    # Send notification
    result = await provider.send(
        recipient="#general",
        content="Direct Discord test message"
    )
    
    assert result.success is True
    assert result.provider == "discord"
    
    # Verify message received
    async with httpx.AsyncClient() as http_client:
        messages_response = await http_client.get("http://localhost:8080/messages")
        messages_data = messages_response.json()
        
        assert messages_data["count"] > 0
        last_message = messages_data["messages"][-1]
        assert last_message["payload"]["content"] == "Direct Discord test message"

