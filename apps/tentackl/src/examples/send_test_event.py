#!/usr/bin/env python3
"""Send a test event to check Redis publishing.

Required environment variables:
    EVENT_SOURCE_API_KEY: API key for the registered event source.
    EVENT_SOURCE_ID: ID of the registered event source.
    TENTACKL_API_BASE: (optional) Base URL for the events API.
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime

async def send_test_event():
    """Send a test event."""
    api_key = os.environ.get("EVENT_SOURCE_API_KEY", "")
    source_id = os.environ.get("EVENT_SOURCE_ID", "")
    if not api_key or not source_id:
        print("❌ Set EVENT_SOURCE_API_KEY and EVENT_SOURCE_ID environment variables")
        return
    
    event_data = {
        "event_type": "test.monitoring",
        "data": {
            "message": "Testing Redis event flow",
            "timestamp": datetime.utcnow().isoformat()
        }
    }
    
    async with aiohttp.ClientSession() as session:
        headers = {"X-API-Key": api_key}
        api_base = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
        url = f"{api_base}/webhook/{source_id}"
        
        async with session.post(url, json=event_data, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ Event sent: {result['event_id']}")
            else:
                text = await resp.text()
                print(f"❌ Failed: {resp.status} - {text}")

if __name__ == "__main__":
    asyncio.run(send_test_event())