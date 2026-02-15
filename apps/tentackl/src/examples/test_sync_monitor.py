#!/usr/bin/env python3
"""Synchronous Redis monitor to verify events are published."""

import redis
import threading
import time
import json

def monitor_redis():
    """Monitor Redis pub/sub in a thread."""
    r = redis.Redis(host='redis', port=6379, decode_responses=True)
    p = r.pubsub()
    p.psubscribe('tentackl:events:*')
    
    print("📡 Monitoring Redis events...\n")
    
    for message in p.listen():
        if message['type'] == 'psubscribe':
            print(f"✅ Subscribed to pattern: {message['pattern']}")
        elif message['type'] == 'pmessage':
            print(f"\n📨 Event received!")
            print(f"   Channel: {message['channel']}")
            print(f"   Pattern: {message['pattern']}")
            try:
                data = json.loads(message['data'])
                print(f"   Type: {data.get('event_type', 'unknown')}")
                print(f"   ID: {data.get('id', 'unknown')}")
            except:
                print(f"   Data: {message['data'][:100]}")


if __name__ == "__main__":
    # Run monitor in thread
    monitor_thread = threading.Thread(target=monitor_redis)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    print("Monitor started. Press Ctrl+C to stop.\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping monitor...")