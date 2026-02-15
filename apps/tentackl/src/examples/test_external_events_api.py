#!/usr/bin/env python3
"""Test script for External Events API.

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


async def test_external_events():
    """Test external events API endpoints."""
    async with aiohttp.ClientSession() as session:
        print("Testing External Events API...\n")
        
        # 1. Health check
        print("1. Testing health endpoint...")
        async with session.get(f"{API_BASE}/health") as resp:
            if resp.status == 200:
                health = await resp.json()
                print(f"✅ Health check passed: {health}")
            else:
                print(f"❌ Health check failed: {resp.status}")
        
        # 2. Register an event source
        print("\n2. Registering event source...")
        source_data = {
            "name": "Test Weather API",
            "source_type": "webhook",
            "endpoint": "/webhooks/weather",
            "authentication_type": "api_key",
            "rate_limit_requests": 10,
            "rate_limit_window_seconds": 60,
            "required_fields": ["temperature", "humidity"],
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
                print(f"❌ Source registration failed: {resp.status}")
                error = await resp.text()
                print(f"   Error: {error}")
                return
        
        # 3. Send webhook event
        print("\n3. Sending webhook event...")
        webhook_data = {
            "event_type": "weather.update",
            "data": {
                "temperature": 32.5,
                "humidity": 75,
                "location": "field-1"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Test with API key authentication
        headers = {"X-API-Key": api_key}
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=webhook_data,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Webhook event sent: {result}")
            else:
                print(f"❌ Webhook event failed: {resp.status}")
                error = await resp.text()
                print(f"   Error: {error}")
        
        # 4. Test batch publishing
        print("\n4. Testing batch event publishing...")
        batch_events = [
            {
                "event_type": "sensor.reading",
                "data": {"sensor_id": f"sensor-{i}", "value": 20 + i*5}
            }
            for i in range(5)
        ]
        
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.post(
            f"{API_BASE}/publish/batch",
            json=batch_events,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Batch published: {result['successful']}/{result['total']} successful")
            else:
                print(f"❌ Batch publish failed: {resp.status}")
        
        # 5. Test event replay
        print("\n5. Testing event replay...")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.get(
            f"{API_BASE}/replay?limit=10",
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Event replay: Found {result['total']} events")
                for event in result['events'][:3]:  # Show first 3
                    print(f"   - {event['event_type']} at {event['timestamp']}")
            else:
                print(f"❌ Event replay failed: {resp.status}")
        
        # 6. Test rate limiting
        print("\n6. Testing rate limiting...")
        print("Sending multiple events to trigger rate limit...")
        
        # Register a source with strict rate limit
        rate_limited_source_data = {
            "name": "Rate Limited Source",
            "source_type": "webhook",
            "authentication_type": "api_key",
            "rate_limit_requests": 3,
            "rate_limit_window_seconds": 5,
            "active": True
        }
        
        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        async with session.post(
            f"{API_BASE}/sources/register",
            json=rate_limited_source_data,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                rl_source_id = result["source_id"]
                rl_api_key = result["api_key"]
                print(f"✅ Rate limited source registered: {rl_source_id}")
            else:
                print(f"❌ Rate limited source registration failed")
                return
        
        # Send events until rate limited
        headers = {"X-API-Key": rl_api_key}
        for i in range(5):
            event_data = {
                "event_type": "test.rate_limit",
                "data": {"index": i}
            }
            
            async with session.post(
                f"{API_BASE}/webhook/{rl_source_id}",
                json=event_data,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    print(f"   Event {i+1}: ✅ Accepted")
                elif resp.status == 429:
                    print(f"   Event {i+1}: ⚠️  Rate limited (expected)")
                    break
                else:
                    print(f"   Event {i+1}: ❌ Failed with status {resp.status}")
        
        print("\n✨ External Events API test completed!")


if __name__ == "__main__":
    asyncio.run(test_external_events())