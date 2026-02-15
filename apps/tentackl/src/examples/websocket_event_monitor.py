#!/usr/bin/env python3
"""
Real-time event monitor using WebSocket streaming.

This example shows how to build a monitoring application that:
- Connects to the event bus via WebSocket
- Receives real-time events
- Filters and processes events
- Maintains statistics

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
from collections import defaultdict
from typing import Dict, Any

API_BASE = os.environ.get("TENTACKL_API_BASE", "http://api:8000/api/events")
WS_BASE = os.environ.get("TENTACKL_WS_BASE", "ws://api:8000/api/events")
ADMIN_TOKEN = os.environ.get("TENTACKL_ADMIN_TOKEN", "")


class EventMonitor:
    """Real-time event monitoring dashboard."""
    
    def __init__(self, source_id: str, api_key: str):
        self.source_id = source_id
        self.api_key = api_key
        self.stats = defaultdict(int)
        self.event_history = []
        self.max_history = 100
        self.running = True
        
    async def connect_and_monitor(self):
        """Connect to WebSocket and monitor events."""
        ws_url = f"{WS_BASE}/ws/{self.source_id}?api_key={self.api_key}"
        
        async with websockets.connect(ws_url) as websocket:
            print(f"📡 Connected to event stream for source: {self.source_id}")
            
            # Handle initial connection
            welcome = await websocket.recv()
            welcome_data = json.loads(welcome)
            print(f"✅ {welcome_data['message']}")
            
            # Create monitoring tasks
            tasks = [
                asyncio.create_task(self.receive_events(websocket)),
                asyncio.create_task(self.send_heartbeat(websocket)),
                asyncio.create_task(self.print_stats()),
                asyncio.create_task(self.simulate_events())
            ]
            
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down monitor...")
                self.running = False
                for task in tasks:
                    task.cancel()
                    
    async def receive_events(self, websocket):
        """Receive and process events from WebSocket."""
        while self.running:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(message)
                
                if data["type"] == "event":
                    event = data["data"]
                    await self.process_event(event)
                elif data["type"] == "pong":
                    self.stats["pongs"] += 1
                    
            except asyncio.TimeoutError:
                print("⚠️  No events received for 30 seconds")
            except Exception as e:
                print(f"❌ Error receiving event: {e}")
                break
                
    async def process_event(self, event: Dict[str, Any]):
        """Process incoming event."""
        event_type = event.get("event_type", "unknown")
        
        # Update statistics
        self.stats["total_events"] += 1
        self.stats[f"type_{event_type}"] += 1
        
        # Store in history
        self.event_history.append({
            "timestamp": datetime.utcnow(),
            "event": event
        })
        
        # Trim history
        if len(self.event_history) > self.max_history:
            self.event_history = self.event_history[-self.max_history:]
        
        # Log special events
        if "error" in event_type.lower():
            print(f"🚨 ERROR EVENT: {event}")
        elif "critical" in event_type.lower():
            print(f"🔴 CRITICAL EVENT: {event}")
        
    async def send_heartbeat(self, websocket):
        """Send periodic heartbeat pings."""
        while self.running:
            await asyncio.sleep(15)
            try:
                await websocket.send(json.dumps({"type": "ping"}))
                self.stats["pings"] += 1
            except:
                break
                
    async def print_stats(self):
        """Print statistics periodically."""
        while self.running:
            await asyncio.sleep(10)
            
            print("\n" + "=" * 50)
            print(f"📊 Event Monitor Statistics - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            
            # Overall stats
            print(f"Total Events: {self.stats['total_events']}")
            print(f"Connection Health: {self.stats['pongs']}/{self.stats['pings']} pongs")
            
            # Event type breakdown
            print("\nEvent Types:")
            for key, value in self.stats.items():
                if key.startswith("type_"):
                    event_type = key.replace("type_", "")
                    print(f"  - {event_type}: {value}")
            
            # Recent events
            if self.event_history:
                print("\nRecent Events (last 5):")
                for item in self.event_history[-5:]:
                    event = item["event"]
                    timestamp = item["timestamp"].strftime("%H:%M:%S")
                    print(f"  [{timestamp}] {event.get('event_type', 'unknown')} - {event.get('data', {})}")
            
            print("=" * 50 + "\n")
            
    async def simulate_events(self):
        """Simulate events for testing."""
        async with aiohttp.ClientSession() as session:
            headers = {"X-API-Key": self.api_key}
            
            event_types = [
                ("sensor.temperature", lambda i: {"temp": 20 + (i % 10), "unit": "C"}),
                ("sensor.humidity", lambda i: {"humidity": 60 + (i % 20), "unit": "%"}),
                ("system.heartbeat", lambda i: {"status": "healthy", "uptime": i * 10}),
                ("alert.threshold", lambda i: {"metric": "cpu", "value": 70 + (i % 30)}),
            ]
            
            i = 0
            while self.running:
                await asyncio.sleep(2)  # Send event every 2 seconds
                
                # Pick event type
                event_type, data_generator = event_types[i % len(event_types)]
                
                event_data = {
                    "event_type": event_type,
                    "data": data_generator(i),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                try:
                    async with session.post(
                        f"{API_BASE}/webhook/{self.source_id}",
                        json=event_data,
                        headers=headers
                    ) as resp:
                        if resp.status != 200:
                            print(f"⚠️  Failed to send simulated event: {resp.status}")
                except Exception as e:
                    print(f"⚠️  Error sending simulated event: {e}")
                
                i += 1


async def main():
    """Set up and run the event monitor."""
    print("🚀 Starting Event Monitor Dashboard\n")
    
    # Register a monitoring source
    async with aiohttp.ClientSession() as session:
        source_data = {
            "name": f"Event Monitor {uuid.uuid4().hex[:8]}",
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
                print(f"✅ Monitor source registered: {source_id}")
            else:
                print("❌ Failed to register monitor source")
                return
    
    # Create and run monitor
    monitor = EventMonitor(source_id, api_key)
    
    print("\n📊 Starting real-time event monitoring...")
    print("Press Ctrl+C to stop\n")
    
    try:
        await monitor.connect_and_monitor()
    except KeyboardInterrupt:
        print("\n✅ Monitor stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")