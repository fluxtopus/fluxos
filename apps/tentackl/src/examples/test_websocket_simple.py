#!/usr/bin/env python3
"""Simple WebSocket connection test.

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

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
WS_BASE = os.environ.get("TENTACKL_WS_BASE", "ws://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_simple_connection():
    """Test basic WebSocket connection."""
    # First register a source
    async with aiohttp.ClientSession() as session:
        print("1. Registering source...")
        source_data = {
            "name": f"WS Test {uuid.uuid4().hex[:8]}",
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
            if resp.status == 200:
                result = await resp.json()
                source_id = result["source_id"]
                api_key = result["api_key"]
                print(f"✅ Source: {source_id}")
                print(f"✅ API Key: {api_key}")
            else:
                print(f"❌ Failed: {resp.status}")
                return
    
    # Try to connect
    print("\n2. Connecting to WebSocket...")
    ws_url = f"{WS_BASE}/ws/{source_id}?api_key={api_key}"
    print(f"URL: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected!")
            
            # Wait for welcome message
            welcome = await asyncio.wait_for(websocket.recv(), timeout=5)
            data = json.loads(welcome)
            print(f"✅ Welcome: {data}")
            
            # Send a ping
            print("\n3. Sending ping...")
            await websocket.send(json.dumps({"type": "ping"}))
            
            # Wait for pong
            pong = await asyncio.wait_for(websocket.recv(), timeout=5)
            data = json.loads(pong)
            print(f"✅ Response: {data}")
            
            print("\n✅ WebSocket test passed!")
            
    except asyncio.TimeoutError:
        print("❌ Timeout waiting for response")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_simple_connection())