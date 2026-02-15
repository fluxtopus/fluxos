"""Full end-to-end test: Mimic API → Tentackl → Discord Mock Server"""

import pytest
import asyncio
import httpx
from fastapi.testclient import TestClient
from src.api.routes.auth import hash_api_key
from src.services.key_encryption import KeyEncryptionService
from src.database.models import User, APIKey, ProviderKey
from unittest.mock import patch, AsyncMock
import uuid


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires running InkPass service for full authentication flow")
async def test_full_flow_mimic_to_discord(client, test_user_annual, db_session):
    """
    Full end-to-end test:
    1. Mimic API receives notification request
    2. Mimic retrieves and decrypts provider key
    3. Mimic calls Tentackl with provider credentials
    4. Tentackl's NotifierAgent uses DiscordProvider
    5. DiscordProvider sends to mock Discord server
    """
    
    # 1. Setup: Create API key for user
    api_key_value = "test-full-flow-api-key"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Full Flow Test API Key",
    )
    db_session.add(api_key)
    
    # 2. Setup: Create Discord provider key (webhook URL points to mock server)
    webhook_url = "http://mock-discord:8080/webhooks/test_id/test_token"
    
    provider_key = ProviderKey(
        user_id=test_user_annual.id,
        provider_type="discord",
        webhook_url=webhook_url,
        is_active=True
    )
    db_session.add(provider_key)
    db_session.commit()
    
    # 3. Clear mock server messages
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            await http_client.delete("http://localhost:8080/messages")
    except Exception:
        pass  # Mock server might not be accessible from test
    
    # 4. Mock Tentackl client to simulate Tentackl calling DiscordProvider
    # In real flow, Tentackl would receive the request and execute NotifierAgent
    # For this test, we'll mock the Tentackl response but verify the flow
    
    with patch('src.clients.tentackl_client.TentacklClient.send_notification') as mock_tentackl:
        # Mock Tentackl returning a workflow ID
        mock_tentackl.return_value = "workflow-run-123"
        
        # 5. Send notification via Mimic API
        print("\n📤 Step 1: Sending notification to Mimic API...")
        response = client.post(
            "/api/v1/send",
            json={
                "recipient": "#general",
                "content": "🎉 Full flow test: Mimic → Tentackl → Discord!",
                "provider": "discord"
            },
            headers={"Authorization": f"Bearer {api_key_value}"}
        )
        
        assert response.status_code == 200, f"API returned {response.status_code}: {response.text}"
        data = response.json()
        assert "delivery_id" in data
        delivery_id = data["delivery_id"]
        
        print(f"✅ Mimic API accepted request, delivery_id: {delivery_id}")
        
        # 6. Verify Tentackl was called with correct parameters
        assert mock_tentackl.called, "Tentackl client should have been called"
        call_args = mock_tentackl.call_args
        
        print(f"\n📋 Step 2: Verifying Tentackl call parameters...")
        print(f"   User ID: {call_args.kwargs.get('user_id')}")
        print(f"   Provider: {call_args.kwargs.get('provider')}")
        print(f"   Recipient: {call_args.kwargs.get('recipient')}")
        print(f"   Content: {call_args.kwargs.get('content')}")
        
        # In the real implementation, provider_credentials would be passed
        # but our mock doesn't capture that. Let's verify the call was made correctly.
        
    # 7. Now test the actual Tentackl → Discord flow
    # This simulates what happens inside Tentackl when it receives the request
    print(f"\n📋 Step 3: Testing Tentackl → Discord flow...")
    
    # Import DiscordProvider from Tentackl
    import sys
    sys.path.insert(0, '/app/../src')  # Adjust path for Tentackl src
    from agents.providers.discord_provider import DiscordProvider
    
    # Use the same webhook URL that Mimic would pass
    provider = DiscordProvider(credentials={"webhook_url": webhook_url})
    
    result = await provider.send(
        recipient="#general",
        content="🎉 Full flow test: Mimic → Tentackl → Discord!"
    )
    
    assert result.success is True, f"Discord provider failed: {result.error}"
    print(f"✅ Discord provider sent successfully")
    
    # 8. Verify message received by mock server
    await asyncio.sleep(1)
    print(f"\n📨 Step 4: Checking mock server for received message...")
    
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        # Try both localhost (from host) and mock-discord (from container)
        for url in ["http://localhost:8080/messages", "http://mock-discord:8080/messages"]:
            try:
                response = await http_client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    print(f"📊 Messages received: {data['count']}")
                    
                    if data['count'] > 0:
                        last_message = data['messages'][-1]
                        content = last_message['payload'].get('content', '')
                        print(f"✅ Message received: {content}")
                        assert "Full flow test" in content
                        return True
            except Exception:
                continue
    
    pytest.fail("Message not received by mock server")


@pytest.mark.integration
@pytest.mark.skip(reason="Requires running InkPass service for full authentication flow")
def test_mimic_api_to_tentackl_integration(client, test_user_annual, db_session):
    """Test that Mimic API correctly calls Tentackl with provider credentials"""
    
    # Setup user, API key, and provider key
    api_key_value = "test-integration-key"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Integration Test Key",
    )
    db_session.add(api_key)
    
    # Create provider key
    webhook_url = "http://mock-discord:8080/webhooks/test_id/test_token"
    provider_key = ProviderKey(
        user_id=test_user_annual.id,
        provider_type="discord",
        webhook_url=webhook_url,
        is_active=True
    )
    db_session.add(provider_key)
    db_session.commit()
    
    # Mock Tentackl client to capture what Mimic sends
    with patch('src.clients.tentackl_client.TentacklClient.send_notification') as mock_send:
        mock_send.return_value = "workflow-123"
        
        # Call Mimic API
        response = client.post(
            "/api/v1/send",
            json={
                "recipient": "#general",
                "content": "Integration test",
                "provider": "discord"
            },
            headers={"Authorization": f"Bearer {api_key_value}"}
        )
        
        assert response.status_code == 200
        
        # Verify Tentackl was called
        assert mock_send.called
        
        # Verify call parameters
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs['user_id'] == test_user_annual.id
        assert call_kwargs['provider'] == "discord"
        assert call_kwargs['recipient'] == "#general"
        assert call_kwargs['content'] == "Integration test"
        
        # In real implementation, provider_credentials would be in the call
        # The TentacklClient retrieves and decrypts them before calling Tentackl

