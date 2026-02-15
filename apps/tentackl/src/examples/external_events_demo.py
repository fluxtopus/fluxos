#!/usr/bin/env python3
"""Demo script showing how to use the External Events API with proper authentication.

Required environment variables:
    TENTACKL_ADMIN_TOKEN: Bearer token for admin authentication (from InkPass login).
    TENTACKL_API_BASE: (optional) Base URL for the events API. Defaults to http://localhost:8000/api/events.
"""

import asyncio
import aiohttp
import json
import os
import uuid
from datetime import datetime

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://localhost:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def demo_external_events():
    """Demonstrate external events API usage with proper authentication."""
    async with aiohttp.ClientSession() as session:
        print("🚀 External Events API Demo\n")
        
        # 1. Register an event source (admin only)
        print("1️⃣ Registering event source...")
        source_data = {
            "name": "IoT Weather Station",
            "source_type": "webhook",
            "endpoint": "/webhooks/weather-station",
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
                print(f"✅ Source registered successfully!")
                print(f"   Source ID: {source_id}")
                print(f"   API Key: {api_key}")
                print(f"   Keep this API key safe - it won't be shown again!\n")
            else:
                print(f"❌ Registration failed: {resp.status}")
                return
        
        # 2. Send authenticated webhook events
        print("2️⃣ Sending authenticated weather data...")
        
        # Simulate weather readings
        weather_readings = [
            {"temperature": 25.5, "humidity": 65, "location": "greenhouse-1"},
            {"temperature": 28.0, "humidity": 70, "location": "field-north"},
            {"temperature": 38.5, "humidity": 85, "location": "field-south"},  # High temp!
        ]
        
        for reading in weather_readings:
            event_data = {
                "event_type": "weather.reading",
                "data": reading,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Authenticate with API key
            headers = {"X-API-Key": api_key}
            async with session.post(
                f"{API_BASE}/webhook/{source_id}",
                json=event_data,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"✅ Weather data sent: {reading['location']} - {reading['temperature']}°C")
                else:
                    print(f"❌ Failed to send data: {resp.status}")
            
            await asyncio.sleep(0.5)  # Small delay between readings
        
        print()
        
        # 3. Test different authentication methods
        print("3️⃣ Testing authentication methods...")
        
        # Bearer token auth
        print("   🔐 Bearer token authentication...")
        headers = {"Authorization": f"Bearer {api_key}"}
        event_data = {
            "event_type": "test.bearer_auth",
            "data": {"message": "Testing bearer auth"}
        }
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            if resp.status == 200:
                print("   ✅ Bearer token auth successful")
            else:
                print(f"   ❌ Bearer token auth failed: {resp.status}")
        
        # Invalid authentication
        print("   🚫 Testing invalid authentication...")
        headers = {"X-API-Key": "wrong-key"}
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            if resp.status == 401:
                print("   ✅ Invalid auth correctly rejected")
            else:
                print(f"   ❌ Unexpected response: {resp.status}")
        
        print()
        
        # 4. Batch event publishing
        print("4️⃣ Sending batch weather alerts...")
        
        # Generate multiple alert events
        alerts = []
        for i in range(10):
            alerts.append({
                "event_type": "weather.alert",
                "data": {
                    "alert_id": str(uuid.uuid4()),
                    "severity": "high" if i < 3 else "medium",
                    "message": f"Temperature anomaly detected in zone {i+1}"
                }
            })
        
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.post(
            f"{API_BASE}/publish/batch",
            json=alerts,
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Batch sent: {result['successful']}/{result['total']} alerts published")
            else:
                print(f"❌ Batch publish failed: {resp.status}")
        
        print()
        
        # 5. Replay events
        print("5️⃣ Replaying recent events...")
        
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.get(
            f"{API_BASE}/replay?event_types=weather.reading,weather.alert&limit=5",
            headers=headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Found {result['total']} recent events:")
                for event in result['events'][:3]:  # Show first 3
                    print(f"   - {event['event_type']} at {event['timestamp'][:19]}")
                if result['total'] > 3:
                    print(f"   ... and {result['total'] - 3} more")
            else:
                print(f"❌ Event replay failed: {resp.status}")
        
        print()
        
        # 6. Test rate limiting
        print("6️⃣ Testing rate limiting...")
        
        # Register a source with strict rate limit
        rate_limited_source_data = {
            "name": "Rate Test Source",
            "source_type": "webhook",
            "authentication_type": "api_key",
            "rate_limit_requests": 5,
            "rate_limit_window_seconds": 10,
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
                print("✅ Rate limited source created (5 requests per 10 seconds)")
            else:
                print(f"❌ Failed to create rate limited source")
                return
        
        # Send events until rate limited
        headers = {"X-API-Key": rl_api_key}
        success_count = 0
        for i in range(7):
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
                    success_count += 1
                    print(f"   Event {i+1}: ✅ Accepted")
                elif resp.status == 429:
                    print(f"   Event {i+1}: ⚠️  Rate limited (as expected)")
                    print(f"   Successfully sent {success_count} events before hitting limit")
                    break
                else:
                    print(f"   Event {i+1}: ❌ Failed with status {resp.status}")
        
        print("\n✨ Demo completed successfully!")
        print("\n📚 Key takeaways:")
        print("   • Always authenticate webhook requests (API key or Bearer token)")
        print("   • Register sources with admin credentials first")
        print("   • Use batch publishing for multiple events")
        print("   • Set appropriate rate limits for your use case")
        print("   • Monitor for 429 responses when rate limited")


if __name__ == "__main__":
    asyncio.run(demo_external_events())