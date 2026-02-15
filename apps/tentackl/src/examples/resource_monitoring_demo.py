#!/usr/bin/env python3
"""
Demonstrate resource monitoring capabilities.

This example shows how Tentackl monitors CPU, memory, disk, and network resources.
"""

import asyncio
import aiohttp
from datetime import datetime
import gc


async def display_resource_metrics():
    """Fetch and display current resource metrics."""
    async with aiohttp.ClientSession() as session:
        async with session.get('http://api:8000/metrics') as response:
            if response.status == 200:
                content = await response.text()
                
                print("\n📊 CURRENT RESOURCE METRICS")
                print("=" * 60)
                
                # Memory metrics
                print("\n💾 MEMORY")
                memory_lines = [l for l in content.split('\n') 
                               if 'tentackl_memory_usage_bytes{' in l]
                for line in memory_lines:
                    if 'process_rss' in line:
                        value = float(line.split()[-1])
                        print(f"  Process RSS: {value/1024/1024:.1f} MB")
                    elif 'system_available' in line:
                        value = float(line.split()[-1])
                        print(f"  System Available: {value/1024/1024/1024:.1f} GB")
                    elif 'gc_objects' in line:
                        value = float(line.split()[-1])
                        print(f"  GC Objects: {int(value)}")
                
                # CPU metrics
                print("\n🔥 CPU")
                cpu_lines = [l for l in content.split('\n') 
                            if 'tentackl_cpu_usage_percent{' in l]
                for line in cpu_lines:
                    if 'component="process"' in line:
                        value = float(line.split()[-1])
                        print(f"  Process CPU: {value:.1f}%")
                    elif 'component="system"' in line:
                        value = float(line.split()[-1])
                        print(f"  System CPU: {value:.1f}%")
                
                # Disk metrics
                print("\n💿 DISK")
                disk_lines = [l for l in content.split('\n') 
                             if 'tentackl_disk_usage_bytes{path="root"' in l]
                disk_values = {}
                for line in disk_lines:
                    if 'type="total"' in line:
                        disk_values['total'] = float(line.split()[-1])
                    elif 'type="used"' in line:
                        disk_values['used'] = float(line.split()[-1])
                    elif 'type="free"' in line:
                        disk_values['free'] = float(line.split()[-1])
                
                if disk_values:
                    total_gb = disk_values.get('total', 0) / 1024**3
                    used_gb = disk_values.get('used', 0) / 1024**3
                    free_gb = disk_values.get('free', 0) / 1024**3
                    percent = (used_gb / total_gb * 100) if total_gb > 0 else 0
                    print(f"  Total: {total_gb:.1f} GB")
                    print(f"  Used: {used_gb:.1f} GB ({percent:.1f}%)")
                    print(f"  Free: {free_gb:.1f} GB")
                
                # File descriptors
                print("\n📁 FILE DESCRIPTORS")
                fd_lines = [l for l in content.split('\n') 
                           if 'tentackl_open_file_descriptors{' in l]
                for line in fd_lines:
                    if 'type="total"' in line:
                        value = int(float(line.split()[-1]))
                        print(f"  Total FDs: {value}")
                    elif 'type="sockets"' in line:
                        value = int(float(line.split()[-1]))
                        print(f"  Sockets: {value}")
                
                # Thread count
                print("\n🧵 THREADS")
                thread_lines = [l for l in content.split('\n') 
                               if 'tentackl_thread_count{' in l]
                for line in thread_lines:
                    if 'state="active"' in line:
                        value = int(float(line.split()[-1]))
                        print(f"  Active threads: {value}")
                    elif 'state="daemon"' in line:
                        value = int(float(line.split()[-1]))
                        print(f"  Daemon threads: {value}")


async def main():
    """Main demo function."""
    print(f"\n🚀 Resource Monitoring Demo - {datetime.now()}")
    print("This demo shows real-time resource monitoring in Tentackl")
    
    # Display initial metrics
    print("\n=== BASELINE METRICS ===")
    await display_resource_metrics()
    
    # Wait for next collection cycle
    print("\n⏳ Waiting 15 seconds for next collection cycle...")
    await asyncio.sleep(15)
    
    # Display updated metrics
    print("\n=== UPDATED METRICS ===")
    await display_resource_metrics()
    
    # Trigger garbage collection to show GC metrics change
    print("\n🗑️ Triggering garbage collection...")
    collected = gc.collect()
    print(f"Collected {collected} objects")
    
    await asyncio.sleep(1)
    
    # Tips for monitoring
    print("\n💡 MONITORING TIPS")
    print("-" * 60)
    print("1. Resource metrics are collected every 10 seconds")
    print("2. Use Prometheus to store historical data")
    print("3. Set up alerts for high resource usage")
    print("4. Monitor trends over time, not just current values")
    print("5. Correlate resource usage with agent execution metrics")
    
    print("\n📈 View full metrics at: http://localhost:8000/metrics")
    print("📊 Grafana dashboards can visualize these metrics over time")
    
    print(f"\n✨ Demo completed - {datetime.now()}")


if __name__ == "__main__":
    asyncio.run(main())