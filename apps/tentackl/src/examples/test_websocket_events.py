#!/usr/bin/env python3
"""Test script demonstrating WebSocket event streaming functionality.

Required environment variables:
    TENTACKL_ADMIN_TOKEN: Bearer token for admin authentication (from InkPass login).
    TENTACKL_API_BASE: (optional) Base URL for the events API.
    TENTACKL_WS_BASE: (optional) WebSocket base URL for the events API.
"""

import asyncio
import websockets
import json
import aiohttp
import os
import uuid
from datetime import datetime

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
WS_BASE = os.environ.get("TENTACKL_WS_BASE", "ws://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


async def test_websocket_streaming():
    """Test WebSocket event streaming functionality."""
    print("🔌 Testing WebSocket Event Streaming\n")
    
    # 1. First register a source and get API key
    async with aiohttp.ClientSession() as session:
        print("1. Registering event source...")
        source_name = f"WebSocket Test {uuid.uuid4().hex[:8]}"
        source_data = {
            "name": source_name,
            "source_type": "webhook",
            "authentication_type": "api_key",
            "rate_limit_requests": 100,
            "rate_limit_window_seconds": 60,
            "required_fields": [],
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
    
    # 2. Connect to WebSocket
    print("\n2. Connecting to WebSocket...")
    ws_url = f"{WS_BASE}/ws/{source_id}?api_key={api_key}"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            # Wait for welcome message
            welcome = await websocket.recv()
            welcome_data = json.loads(welcome)
            print(f"✅ Connected! Received: {welcome_data['message']}")
            
            # 3. Create tasks for sending/receiving
            async def send_test_events():
                """Send test events via HTTP while connected."""
                async with aiohttp.ClientSession() as session:
                    headers = {"X-API-Key": api_key}
                    
                    print("\n3. Sending test events...")
                    for i in range(5):
                        await asyncio.sleep(1)  # Space out events
                        
                        event_data = {
                            "event_type": "test.websocket",
                            "data": {
                                "index": i,
                                "message": f"Test event {i}",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        }
                        
                        async with session.post(
                            f"{API_BASE}/webhook/{source_id}",
                            json=event_data,
                            headers=headers
                        ) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                print(f"   📤 Sent event {i}: {result['event_id']}")
                            else:
                                print(f"   ❌ Failed to send event {i}: {resp.status}")
            
            async def receive_events():
                """Receive events from WebSocket."""
                print("\n4. Listening for events...")
                event_count = 0
                
                try:
                    while event_count < 5:
                        message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        data = json.loads(message)
                        
                        if data["type"] == "event":
                            event_count += 1
                            event = data["event"]
                            print(f"   📥 Received event: {event.get('event_type', 'unknown')} - {event.get('data', {})}")
                        elif data["type"] == "connected":
                            print(f"   ℹ️  {data['message']}")
                        else:
                            print(f"   🔔 Message: {data}")
                            
                except asyncio.TimeoutError:
                    print("   ⏱️  Timeout waiting for events")
                    
                return event_count
            
            async def send_ping():
                """Send periodic ping to keep connection alive."""
                while True:
                    await asyncio.sleep(5)
                    await websocket.send(json.dumps({"type": "ping"}))
                    print("   🏓 Ping sent")
            
            # Run sender and receiver concurrently
            ping_task = asyncio.create_task(send_ping())
            
            try:
                sender_task = asyncio.create_task(send_test_events())
                receiver_task = asyncio.create_task(receive_events())
                
                # Wait for both to complete
                await sender_task
                received_count = await receiver_task
                
                print(f"\n✨ WebSocket test completed! Received {received_count} events.")
                
            finally:
                ping_task.cancel()
                
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def test_websocket_subscription_patterns():
    """Test WebSocket subscription pattern updates."""
    print("\n🔍 Testing WebSocket Subscription Patterns\n")
    
    # Register a source
    async with aiohttp.ClientSession() as session:
        source_data = {
            "name": f"Pattern Test {uuid.uuid4().hex[:8]}",
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
            if resp.status == 200:
                result = await resp.json()
                source_id = result["source_id"]
                api_key = result["api_key"]
            else:
                print("Failed to register source")
                return
    
    # Connect and test subscription updates
    ws_url = f"{WS_BASE}/ws/{source_id}?api_key={api_key}"
    
    try:
        async with websockets.connect(ws_url) as websocket:
            # Wait for welcome
            await websocket.recv()
            
            print("1. Sending subscription update...")
            await websocket.send(json.dumps({
                "type": "subscribe",
                "pattern": "weather.*"
            }))
            
            # Wait for response
            response = await websocket.recv()
            data = json.loads(response)
            if data["type"] == "subscription_updated":
                print(f"✅ Subscription updated to pattern: {data['pattern']}")
            
            print("\n2. Testing ping/pong...")
            await websocket.send(json.dumps({"type": "ping"}))
            
            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            data = json.loads(response)
            if data["type"] == "pong":
                print("✅ Pong received!")
                
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run all WebSocket tests."""
    print("=" * 60)
    print("WebSocket Event Streaming Tests")
    print("=" * 60)
    
    # Test basic streaming
    await test_websocket_streaming()
    
    # Test subscription patterns
    await test_websocket_subscription_patterns()
    
    print("\n✅ All WebSocket tests completed!")


if __name__ == "__main__":
    asyncio.run(main())