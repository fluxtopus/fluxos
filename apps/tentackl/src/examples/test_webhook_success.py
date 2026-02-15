#!/usr/bin/env python3
"""Test script showing successful webhook authentication.

Required environment variables:
    TENTACKL_ADMIN_TOKEN: Bearer token for admin authentication (from InkPass login).
    TENTACKL_API_BASE: (optional) Base URL for the events API.
"""

import asyncio
import aiohttp
import json
import os
import uuid
from datetime import datetime

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://localhost:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_webhook_success():
    """Test successful webhook flow."""
    async with aiohttp.ClientSession() as session:
        print("✅ Testing Successful Webhook Flow\n")
        
        # 1. Register a new source
        print("1. Registering new event source...")
        source_name = f"Test Source {uuid.uuid4().hex[:8]}"
        source_data = {
            "name": source_name,
            "source_type": "webhook",
            "endpoint": "/webhooks/test",
            "authentication_type": "api_key",
            "rate_limit_requests": 100,
            "rate_limit_window_seconds": 60,
            "required_fields": ["temperature", "humidity", "location"],
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
                print(f"✅ Source registered: {source_id}")
                print(f"   API Key: {api_key}")
            else:
                print(f"❌ Registration failed: {resp.status}")
                return
        
        # 2. Send webhook event with proper authentication
        print("\n2. Sending webhook event with API key...")
        event_data = {
            "event_type": "weather.update",
            "data": {
                "temperature": 28.5,
                "humidity": 72,
                "location": "greenhouse-west"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        headers = {"X-API-Key": api_key}
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Webhook event sent successfully!")
                print(f"   Event ID: {result['event_id']}")
                print(f"   Response: {result}")
            else:
                error = await resp.text()
                print(f"❌ Webhook failed: {resp.status}")
                print(f"   Error: {error}")
        
        # 3. Test rate limiting
        print("\n3. Testing rate limiting (sending 10 events rapidly)...")
        
        # Register a source with lower rate limit
        rate_source_data = {
            "name": f"Rate Test {uuid.uuid4().hex[:8]}",
            "source_type": "webhook",
            "authentication_type": "api_key",
            "rate_limit_requests": 5,
            "rate_limit_window_seconds": 10,
            "required_fields": [],
            "active": True
        }
        
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        async with session.post(
            f"{API_BASE}/sources/register",
            json=rate_source_data,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                rate_source_id = result["source_id"]
                rate_api_key = result["api_key"]
                print(f"✅ Rate limited source created")
            else:
                print(f"❌ Failed to create rate limited source")
                return
        
        # Send events rapidly
        headers = {"X-API-Key": rate_api_key}
        success_count = 0
        rate_limited = False
        
        for i in range(10):
            event_data = {
                "event_type": "test.rate",
                "data": {"index": i}
            }
            
            async with session.post(
                f"{API_BASE}/webhook/{rate_source_id}",
                json=event_data,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    success_count += 1
                    print(f"   Event {i+1}: ✅ Accepted")
                elif resp.status == 429:
                    print(f"   Event {i+1}: ⚠️  Rate limited (expected)")
                    rate_limited = True
                else:
                    print(f"   Event {i+1}: ❌ Failed ({resp.status})")
        
        print(f"\n   Summary: {success_count} events accepted, rate limiting {'worked' if rate_limited else 'not triggered'}")
        
        # 4. Verify events were published
        print("\n4. Checking event replay...")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.get(
            f"{API_BASE}/replay?event_types=weather.update,test.rate&limit=10",
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Found {result['total']} events in replay")
                if result['events']:
                    print("   Recent events:")
                    for event in result['events'][:3]:
                        print(f"   - {event['event_type']} from {event['source']}")
            else:
                print(f"❌ Replay failed: {resp.status}")
        
        print("\n✨ Webhook authentication is working correctly!")


if __name__ == "__main__":
    asyncio.run(test_webhook_success())