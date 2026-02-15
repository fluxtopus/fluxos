#!/usr/bin/env python3
"""Debug WebSocket event streaming.

Required environment variables:
    TENTACKL_ADMIN_TOKEN: Bearer token for admin authentication (from InkPass login).
    TENTACKL_API_BASE: (optional) Base URL for the events API.
    TENTACKL_WS_BASE: (optional) WebSocket base URL for the events API.
"""

import asyncio
import websockets
import json
import aiohttp
import os
import uuid
from datetime import datetime

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
WS_BASE = os.environ.get("TENTACKL_WS_BASE", "ws://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_websocket_debug():
    """Debug WebSocket event streaming."""
    # 1. Register source
    async with aiohttp.ClientSession() as session:
        print("1. Registering source...")
        source_data = {
            "name": f"Debug Test {uuid.uuid4().hex[:8]}",
            "source_type": "webhook",
            "authentication_type": "api_key",
            "active": True
        }
        
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        async with session.post(
            f"{API_BASE}/sources/register",
            json=source_data,
            headers=headers
        ) as resp:
            result = await resp.json()
            source_id = result["source_id"]
            api_key = result["api_key"]
            print(f"✅ Source: {source_id}")
    
    # 2. Connect WebSocket
    print("\n2. Connecting WebSocket...")
    ws_url = f"{WS_BASE}/ws/{source_id}?api_key={api_key}"
    
    async with websockets.connect(ws_url) as websocket:
        # Get welcome message
        welcome = await websocket.recv()
        print(f"✅ Connected: {json.loads(welcome)['message']}")
        
        # 3. Send test event in background
        async def send_event():
            await asyncio.sleep(2)  # Wait 2 seconds
            print("\n3. Sending test event via webhook...")
            
            async with aiohttp.ClientSession() as session:
                event_data = {
                    "event_type": "test.debug",
                    "data": {
                        "message": "Debug test event",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
                
                headers = {"X-API-Key": api_key}
                async with session.post(
                    f"{API_BASE}/webhook/{source_id}",
                    json=event_data,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"✅ Event sent: {result['event_id']}")
                    else:
                        print(f"❌ Failed to send: {resp.status}")
        
        # Start event sender
        sender_task = asyncio.create_task(send_event())
        
        # 4. Listen for events
        print("\n4. Waiting for events (10 second timeout)...")
        try:
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)
                    
                    if data["type"] == "event":
                        print(f"✅ Received event!")
                        print(f"   Data: {data}")
                        break  # Exit after receiving one event
                    else:
                        print(f"ℹ️  Received: {data['type']}")
                        
                except asyncio.TimeoutError:
                    print("⏱️  Timeout - no events received")
                    break
                    
        finally:
            await sender_task  # Ensure sender completes
            
        print("\n✅ Debug test completed")


if __name__ == "__main__":
    asyncio.run(test_websocket_debug())