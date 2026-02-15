#!/usr/bin/env python3
"""Monitor Redis events to debug WebSocket issues."""

import asyncio
import redis.asyncio as redis_async
import json

async def monitor_redis():
    """Monitor all Redis pub/sub events."""
    print("Monitoring Redis pub/sub events...\n")
    
    client = await redis_async.from_url("redis://redis:6379", decode_responses=True)
    pubsub = client.pubsub()
    
    # Subscribe to all tentackl events
    pattern = "tentackl:events:*"
    await pubsub.psubscribe(pattern)
    print(f"Subscribed to pattern: {pattern}")
    
    print("\nListening for events (press Ctrl+C to stop)...\n")
    
    try:
        async for message in pubsub.listen():
            if message['type'] in ['pmessage', 'psubscribe']:
                if message['type'] == 'psubscribe':
                    print(f"✅ Subscribed to: {message['pattern']}")
                else:
                    print(f"\n📨 Event received!")
                    print(f"   Channel: {message['channel']}")
                    print(f"   Pattern: {message['pattern']}")
                    try:
                        data = json.loads(message['data'])
                        print(f"   Event ID: {data.get('id')}")
                        print(f"   Event Type: {data.get('event_type')}")
                        print(f"   Source: {data.get('source')}")
                        print(f"   Data: {data.get('data')}")
                    except:
                        print(f"   Raw data: {message['data']}")
                        
    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
    finally:
        await pubsub.unsubscribe()
        await client.close()


if __name__ == "__main__":
    asyncio.run(monitor_redis())