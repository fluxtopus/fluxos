#!/usr/bin/env python3
"""Debug script to test webhook authentication directly.

Required environment variables:
    EVENT_SOURCE_API_KEY: API key for the registered event source.
    EVENT_SOURCE_ID: ID of the registered event source.
    TENTACKL_API_BASE: (optional) Base URL for the events API.
"""

import asyncio
import aiohttp
import json
import hashlib
import os

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://localhost:8000/api/events")


async def debug_webhook_auth():
    """Debug webhook authentication."""
    print("🔍 Debugging Webhook Authentication\n")

    source_id = os.environ.get("EVENT_SOURCE_ID", "")
    api_key = os.environ.get("EVENT_SOURCE_API_KEY", "")
    if not source_id or not api_key:
        print("❌ Set EVENT_SOURCE_ID and EVENT_SOURCE_API_KEY environment variables")
        return
    
    # Calculate what the hash should be
    expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
    print(f"API Key: {api_key}")
    print(f"Expected Hash: {expected_hash}\n")
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Direct webhook call with API key
        print("1. Testing webhook with X-API-Key header...")
        event_data = {
            "event_type": "weather.update",
            "data": {
                "temperature": 25.5,
                "humidity": 65,
                "location": "test-location"
            }
        }
        
        headers = {"X-API-Key": api_key}
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            print(f"   Status: {resp.status}")
            if resp.status != 200:
                error = await resp.text()
                print(f"   Error: {error}")
            else:
                result = await resp.json()
                print(f"   Success: {result}")
        
        # Test 2: Try with Bearer token
        print("\n2. Testing webhook with Bearer token...")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            print(f"   Status: {resp.status}")
            if resp.status != 200:
                error = await resp.text()
                print(f"   Error: {error}")
        
        # Test 3: Check what headers are being sent
        print("\n3. Echo test - what headers is the server seeing?")
        headers = {
            "X-API-Key": api_key,
            "X-Test-Header": "test-value"
        }
        async with session.post(
            f"{API_BASE}/webhook/{source_id}",
            json=event_data,
            headers=headers
        ) as resp:
            print(f"   Status: {resp.status}")
            # Server logs should show the headers


if __name__ == "__main__":
    asyncio.run(debug_webhook_auth())