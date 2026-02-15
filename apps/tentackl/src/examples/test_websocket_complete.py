#!/usr/bin/env python3
"""Complete WebSocket event streaming test with all components.

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
import redis.asyncio as redis_async

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
WS_BASE = os.environ.get("TENTACKL_WS_BASE", "ws://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_complete_flow():
    """Test complete WebSocket event flow."""
    print("🧪 Complete WebSocket Event Test\n")
    
    # 1. Register source
    async with aiohttp.ClientSession() as session:
        print("1. Registering source...")
        source_data = {
            "name": f"Complete Test {uuid.uuid4().hex[:8]}",
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
    
    # 2. Start Redis monitor
    print("\n2. Starting Redis monitor...")
    redis_client = await redis_async.from_url("redis://redis:6379", decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("tentackl:eventbus:events:*")
    
    redis_events = []
    
    async def monitor_redis():
        async for message in pubsub.listen():
            if message['type'] == 'pmessage':
                redis_events.append(message)
                print(f"   📡 Redis: {message['channel']}")
    
    monitor_task = asyncio.create_task(monitor_redis())
    
    # 3. Connect WebSocket
    print("\n3. Connecting WebSocket...")
    ws_url = f"{WS_BASE}/ws/{source_id}?api_key={api_key}"
    
    async with websockets.connect(ws_url) as websocket:
        # Get welcome
        welcome = await websocket.recv()
        print(f"✅ WebSocket connected")
        
        ws_events = []
        
        async def listen_ws():
            try:
                while True:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data["type"] == "event":
                        ws_events.append(data)
                        print(f"   📨 WebSocket: Received event!")
            except asyncio.TimeoutError:
                pass
        
        ws_task = asyncio.create_task(listen_ws())
        
        # 4. Send events
        print("\n4. Sending test events...")
        await asyncio.sleep(1)  # Let listeners start
        
        async with aiohttp.ClientSession() as session:
            headers = {"X-API-Key": api_key}
            
            # Send multiple events
            for i in range(3):
                event_data = {
                    "event_type": f"test.complete.{i}",
                    "data": {
                        "index": i,
                        "message": f"Test event {i}",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
                
                async with session.post(
                    f"{API_BASE}/webhook/{source_id}",
                    json=event_data,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"   ✅ Sent event {i}: {result['event_id']}")
                    else:
                        print(f"   ❌ Failed {i}: {resp.status}")
                
                await asyncio.sleep(0.5)  # Small delay between events
        
        # 5. Wait and collect results
        print("\n5. Waiting for events...")
        await asyncio.sleep(3)
        
        # Cancel tasks
        ws_task.cancel()
        monitor_task.cancel()
        
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    
    # 6. Report results
    print("\n📊 Results:")
    print(f"   Redis events received: {len(redis_events)}")
    print(f"   WebSocket events received: {len(ws_events)}")
    
    if redis_events:
        print("\n   Redis channels:")
        for evt in redis_events[:5]:  # First 5
            print(f"     - {evt['channel']}")
    
    if ws_events:
        print("\n   WebSocket events:")
        for evt in ws_events:
            print(f"     - Type: {evt['type']}, Data keys: {list(evt.get('data', {}).keys())}")
    
    # Cleanup
    await pubsub.unsubscribe()
    await redis_client.aclose()
    
    # Final verdict
    success = len(ws_events) > 0
    print(f"\n{'✅' if success else '❌'} WebSocket streaming {'working' if success else 'not working'}!")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(test_complete_flow())
    exit(0 if result else 1)