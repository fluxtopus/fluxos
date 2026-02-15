#!/usr/bin/env python3
"""
Test resource metrics collection.

This script verifies that CPU, memory, disk, and network metrics are being collected.
"""

import asyncio
import aiohttp
import time
import psutil
from datetime import datetime


async def check_resource_metrics():
    """Check resource metrics from the endpoint."""
    async with aiohttp.ClientSession() as session:
        async with session.get('http://api:8000/metrics') as response:
            if response.status == 200:
                content = await response.text()
                
                # Resource metrics to check
                resource_metrics = {
                    "tentackl_memory_usage_bytes": "Memory usage",
                    "tentackl_cpu_usage_percent": "CPU usage",
                    "tentackl_disk_usage_bytes": "Disk usage",
                    "tentackl_disk_io_operations_total": "Disk I/O",
                    "tentackl_network_bytes_total": "Network traffic",
                    "tentackl_open_file_descriptors": "File descriptors",
                    "tentackl_thread_count": "Thread count"
                }
                
                print("\n📊 RESOURCE METRICS STATUS")
                print("=" * 60)
                
                for metric_name, description in resource_metrics.items():
                    lines = [l for l in content.split('\n') 
                            if metric_name in l and not l.startswith('#')]
                    
                    if lines:
                        print(f"\n✅ {description} ({metric_name}):")
                        # Show first few entries
                        for line in lines[:5]:
                            # Parse the value
                            parts = line.split()
                            if len(parts) >= 2:
                                value = parts[-1]
                                labels = line[len(metric_name):].split()[0] if '{' in line else ""
                                print(f"   {labels} = {value}")
                    else:
                        print(f"\n❌ {description} ({metric_name}): Not found")
                
                # Show system info
                print("\n📈 SYSTEM INFO")
                print("-" * 60)
                system_lines = [l for l in content.split('\n') 
                               if 'tentackl_system_info' in l and not l.startswith('#')]
                if system_lines:
                    print(system_lines[0])
                    
                return True
            else:
                print(f"❌ Failed to fetch metrics: HTTP {response.status}")
                return False


async def simulate_resource_usage():
    """Simulate some resource usage to generate metrics."""
    print(f"\n🚀 Starting resource metrics test at {datetime.now()}")
    
    # Wait for initial metrics collection (10s interval)
    print("\n⏳ Waiting for initial metrics collection...")
    await asyncio.sleep(12)
    
    # Check initial metrics
    print("\n=== INITIAL METRICS ===")
    await check_resource_metrics()
    
    # Generate some load
    print("\n🔥 Generating resource load...")
    
    # CPU load
    print("  - CPU: Calculating prime numbers...")
    start = time.time()
    primes = []
    for num in range(2, 10000):
        if all(num % i != 0 for i in range(2, int(num**0.5) + 1)):
            primes.append(num)
    print(f"  ✓ Found {len(primes)} primes in {time.time()-start:.2f}s")
    
    # Memory allocation
    print("  - Memory: Allocating large list...")
    data = [i for i in range(1000000)]
    print(f"  ✓ Allocated {len(data)} items")
    
    # Disk I/O
    print("  - Disk: Writing temporary file...")
    with open('/tmp/test_metrics.dat', 'w') as f:
        for i in range(10000):
            f.write(f"Line {i}: {'x' * 100}\n")
    print("  ✓ Wrote test file")
    
    # Network (simulated via metrics endpoint calls)
    print("  - Network: Making HTTP requests...")
    async with aiohttp.ClientSession() as session:
        for i in range(5):
            async with session.get('http://api:8000/health/metrics') as resp:
                await resp.text()
    print("  ✓ Made 5 HTTP requests")
    
    # Wait for metrics to update
    print("\n⏳ Waiting for metrics update...")
    await asyncio.sleep(12)
    
    # Check metrics after load
    print("\n=== METRICS AFTER LOAD ===")
    await check_resource_metrics()
    
    # Cleanup
    import os
    try:
        os.remove('/tmp/test_metrics.dat')
    except:
        pass
    
    # System stats
    print("\n📊 CURRENT SYSTEM STATS")
    print("-" * 60)
    print(f"CPU Usage: {psutil.cpu_percent(interval=1)}%")
    print(f"Memory Usage: {psutil.virtual_memory().percent}%")
    print(f"Disk Usage (/): {psutil.disk_usage('/').percent}%")
    
    print(f"\n✨ Resource metrics test completed at {datetime.now()}")


if __name__ == "__main__":
    asyncio.run(simulate_resource_usage())