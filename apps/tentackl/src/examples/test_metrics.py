#!/usr/bin/env python3
"""Test script to verify Prometheus metrics are working."""

import asyncio
import aiohttp
from datetime import datetime


async def test_metrics():
    """Test the metrics endpoint."""
    print(f"[{datetime.now()}] Testing Prometheus metrics endpoint...")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test metrics endpoint
            async with session.get('http://api:8000/metrics') as response:
                if response.status == 200:
                    content = await response.text()
                    print(f"[{datetime.now()}] ✅ Metrics endpoint is working!")
                    print("\n--- Sample Metrics ---")
                    # Show first 1000 chars
                    print(content[:1000])
                    print("\n--- Looking for our custom metrics ---")
                    
                    # Check for our custom metrics
                    metrics_to_check = [
                        "agent_executions",
                        "agent_execution_duration",
                        "workflow_active",
                        "workflow_duration",
                        "errors_total",
                        "event_bus_messages",
                        "redis_operations",
                        "db_operations"
                    ]
                    
                    for metric in metrics_to_check:
                        if metric in content:
                            print(f"✅ Found metric: {metric}")
                            # Show lines containing this metric
                            for line in content.split('\n'):
                                if metric in line and not line.startswith('#'):
                                    print(f"   {line}")
                        else:
                            print(f"❌ Missing metric: {metric}")
                            
                else:
                    print(f"[{datetime.now()}] ❌ Metrics endpoint returned status: {response.status}")
                    print(await response.text())
                    
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Error accessing metrics endpoint: {e}")
            
    print(f"\n[{datetime.now()}] Test completed!")


if __name__ == "__main__":
    asyncio.run(test_metrics())