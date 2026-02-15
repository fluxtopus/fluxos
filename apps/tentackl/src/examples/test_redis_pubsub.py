#!/usr/bin/env python3
"""Test Redis pub/sub to understand event flow.

Required environment variables:
    TENTACKL_ADMIN_TOKEN: Bearer token for admin authentication (from InkPass login).
    TENTACKL_API_BASE: (optional) Base URL for the events API.
"""

import asyncio
import redis.asyncio as redis_async
import json
import aiohttp
import os
import uuid
from datetime import datetime

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_redis_pubsub():
    """Test Redis pub/sub event flow."""
    # 1. Register a source
    async with aiohttp.ClientSession() as session:
        print("1. Registering source...")
        source_data = {
            "name": f"PubSub Test {uuid.uuid4().hex[:8]}",
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
    
    # Subscribe to all events
    await pubsub.psubscribe("tentackl:events:*")
    print("✅ Subscribed to tentackl:events:*")
    
    # 3. Send event after delay
    async def send_event():
        await asyncio.sleep(1)
        print("\n3. Sending test event...")
        
        async with aiohttp.ClientSession() as session:
            event_data = {
                "event_type": "test.pubsub",
                "data": {
                    "message": "Testing pub/sub flow",
                    "source_id": source_id
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
                    print(f"❌ Failed: {resp.status}")
    
    # Start sender
    sender_task = asyncio.create_task(send_event())
    
    # 4. Listen for events
    print("\n4. Listening for events...")
    event_count = 0
    start_time = asyncio.get_event_loop().time()
    
    try:
        async for message in pubsub.listen():
            if message['type'] == 'pmessage':
                event_count += 1
                print(f"\n📨 Event {event_count} received!")
                print(f"   Channel: {message['channel']}")
                
                try:
                    data = json.loads(message['data'])
                    print(f"   Type: {data.get('event_type')}")
                    print(f"   Source: {data.get('source')}")
                except:
                    print(f"   Data: {message['data']}")
                
                # Exit after receiving events
                if event_count >= 2:  # Should get at least 2 (all + type-specific)
                    break
                    
            # Timeout after 5 seconds
            if asyncio.get_event_loop().time() - start_time > 5:
                print("\n⏱️  Timeout")
                break
                
    finally:
        await sender_task
        await pubsub.unsubscribe()
        await redis_client.close()
        
    print(f"\n✅ Test completed - received {event_count} events")


if __name__ == "__main__":
    asyncio.run(test_redis_pubsub())