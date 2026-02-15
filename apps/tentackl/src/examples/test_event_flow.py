#!/usr/bin/env python3
"""Test complete event flow with detailed logging."""

import asyncio
import redis.asyncio as redis_async
import json
from src.event_bus.redis_event_bus import RedisEventBus
from src.interfaces.event_bus import Event, EventSourceType
from datetime import datetime

async def test_event_flow():
    """Test event publishing and subscription."""
    print("Testing Event Bus flow...\n")
    
    # 1. Create event bus instance
    event_bus = RedisEventBus()
    await event_bus.start()
    print("✅ Event Bus started")
    
    # 2. Start Redis monitor in background
    redis_client = await redis_async.from_url("redis://redis:6379", decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("tentackl:events:*")
    print("✅ Redis monitor subscribed")
    
    received_events = []
    
    async def monitor_redis():
        async for message in pubsub.listen():
            if message['type'] == 'pmessage':
                print(f"\n📨 Redis event on channel: {message['channel']}")
                received_events.append(message)
    
    # Start monitor
    monitor_task = asyncio.create_task(monitor_redis())
    
    # 3. Publish test event
    await asyncio.sleep(1)  # Let monitor start
    
    print("\nPublishing test event...")
    event = Event(
        source="test-script",
        source_type=EventSourceType.INTERNAL,
        event_type="test.flow",
        data={"message": "Testing event flow", "timestamp": datetime.utcnow().isoformat()}
    )
    
    success = await event_bus.publish(event)
    print(f"✅ Event published: {success}, ID: {event.id}")
    
    # 4. Wait for events to be received
    await asyncio.sleep(2)
    
    print(f"\n📊 Received {len(received_events)} events via Redis")
    for evt in received_events:
        print(f"   - Channel: {evt['channel']}")
    
    # Cleanup
    monitor_task.cancel()
    await pubsub.unsubscribe()
    await redis_client.close()
    await event_bus.stop()
    
    print("\n✅ Test completed")


if __name__ == "__main__":
    asyncio.run(test_event_flow())