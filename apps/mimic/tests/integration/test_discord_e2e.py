"""End-to-end test for Discord notification with mock server.

NOTE: This test depends on the legacy src.agents.providers module which no
longer exists in Mimic. It is skipped automatically until the provider is
migrated to the new integration system.
"""

import pytest
import asyncio
import httpx
import subprocess
import time
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Guard: skip collection if the legacy provider module is missing
DiscordProvider = pytest.importorskip(
    "src.agents.providers.discord_provider",
    reason="Legacy DiscordProvider not available in current Mimic",
).DiscordProvider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discord_with_mock_server():
    """Test Discord notification delivery with mock server"""
    
    # Mock server URL (should be running on port 8080)
    mock_server_url = "http://localhost:8080"
    webhook_url = f"{mock_server_url}/webhooks/test_webhook_id/test_webhook_token"
    
    # Clear previous messages
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.delete(f"{mock_server_url}/messages")
    except Exception:
        pass  # Server might not be running yet
    
    # Create Discord provider
    provider = DiscordProvider(credentials={"webhook_url": webhook_url})
    
    # Send notification
    print("📤 Sending Discord notification...")
    result = await provider.send(
        recipient="#general",
        content="🎉 Test notification from Mimic notification service!"
    )
    
    assert result.success is True, f"Notification failed: {result.error}"
    assert result.provider == "discord"
    
    # Wait a bit for async processing
    await asyncio.sleep(1)
    
    # Verify message was received
    print("📨 Checking mock server for received messages...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{mock_server_url}/messages")
        assert response.status_code == 200
        
        data = response.json()
        assert data["count"] > 0, "No messages received by mock server"
        
        # Check the last message
        last_message = data["messages"][-1]
        assert "payload" in last_message
        payload = last_message["payload"]
        
        assert payload["content"] == "🎉 Test notification from Mimic notification service!"
        
        print(f"✅ SUCCESS: Message received! Content: {payload['content']}")
        print(f"📊 Total messages received: {data['count']}")
        
        return True

