#!/usr/bin/env python3
"""Direct Redis test."""

import redis
import json
from datetime import datetime

# Use sync Redis client for simplicity
r = redis.Redis(host='redis', port=6379, decode_responses=True)

print("Testing Redis connection...")
r.ping()
print("✅ Redis connected")

# Publish a test event directly
channel = "tentackl:events:all"
event_data = {
    "id": "test-123",
    "event_type": "test.direct",
    "source": "direct-test",
    "data": {"message": "Direct Redis test"},
    "timestamp": datetime.utcnow().isoformat()
}

print(f"\nPublishing to channel: {channel}")
subscribers = r.publish(channel, json.dumps(event_data))
print(f"✅ Published to {subscribers} subscribers")

# Check if event was stored
event_key = "tentackl:event:test-123"
if r.exists(event_key):
    print(f"✅ Event stored at key: {event_key}")
else:
    print(f"❌ Event not found at key: {event_key}")

print("\n✅ Direct Redis test completed")