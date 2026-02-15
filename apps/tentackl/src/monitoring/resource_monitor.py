"""
Resource monitoring for Tentackl.

Collects CPU, memory, disk, and network usage metrics.
"""

import asyncio
import psutil
import os
import time
from typing import Dict, Optional
import structlog
from datetime import datetime

from .metrics import (
    MetricsCollector, 
    memory_usage,
    cpu_usage,
    connection_pool_size,
    connection_pool_active,
    Gauge,
    Counter
)

logger = structlog.get_logger()

# Additional resource metrics
disk_usage = Gauge(
    'tentackl_disk_usage_bytes',
    'Disk usage in bytes',
    ['path', 'type']  # type: used, free, total
)

disk_io_operations = Counter(
    'tentackl_disk_io_operations_total',
    'Total disk I/O operations',
    ['operation', 'disk']  # operation: read, write
)

network_bytes = Counter(
    'tentackl_network_bytes_total',
    'Total network bytes transferred',
    ['interface', 'direction']  # direction: sent, received
)

open_file_descriptors = Gauge(
    'tentackl_open_file_descriptors',
    'Number of open file descriptors',
    ['type']  # type: files, sockets, pipes
)

thread_count = Gauge(
    'tentackl_thread_count',
    'Number of active threads',
    ['state']  # state: active, daemon
)

# Connection pool metrics are already defined in metrics.py


class ResourceMonitor:
    """Monitor system resources and update metrics."""
    
    def __init__(self, interval: int = 10):
        """
        Initialize resource monitor.
        
        Args:
            interval: Collection interval in seconds
        """
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._process = psutil.Process()
        self._last_cpu_times = None
        self._last_disk_io = None
        self._last_net_io = None
        self._start_time = time.time()
        
    async def start(self):
        """Start monitoring resources."""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource monitor started", interval=self.interval)
        
    async def stop(self):
        """Stop monitoring resources."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error("Error collecting resource metrics", error=str(e))
                await asyncio.sleep(self.interval)
                
    async def _collect_metrics(self):
        """Collect all resource metrics."""
        # Run collection in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._collect_sync_metrics)
        
    def _collect_sync_metrics(self):
        """Synchronously collect metrics (runs in thread pool)."""
        try:
            # Process-level metrics
            self._collect_memory_metrics()
            self._collect_cpu_metrics()
            self._collect_thread_metrics()
            self._collect_fd_metrics()
            
            # System-level metrics
            self._collect_disk_metrics()
            self._collect_network_metrics()
            
            # Application-level metrics
            self._collect_connection_pool_metrics()
            
        except Exception as e:
            logger.error("Error in metrics collection", error=str(e))
            
    def _collect_memory_metrics(self):
        """Collect memory usage metrics."""
        try:
            # Process memory
            mem_info = self._process.memory_info()
            memory_usage.labels(component="process_rss").set(mem_info.rss)
            memory_usage.labels(component="process_vms").set(mem_info.vms)
            
            # System memory
            system_mem = psutil.virtual_memory()
            memory_usage.labels(component="system_total").set(system_mem.total)
            memory_usage.labels(component="system_available").set(system_mem.available)
            memory_usage.labels(component="system_used").set(system_mem.used)
            
            # Python-specific memory (if available)
            try:
                import gc
                memory_usage.labels(component="gc_objects").set(
                    sum(gc.get_count())
                )
            except:
                pass
                
        except Exception as e:
            logger.error("Error collecting memory metrics", error=str(e))
            
    def _collect_cpu_metrics(self):
        """Collect CPU usage metrics."""
        try:
            # Process CPU
            cpu_percent = self._process.cpu_percent(interval=0.1)
            cpu_usage.labels(component="process").set(cpu_percent)
            
            # System CPU
            system_cpu = psutil.cpu_percent(interval=0.1, percpu=False)
            cpu_usage.labels(component="system").set(system_cpu)
            
            # Per-CPU core metrics
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            for i, percent in enumerate(cpu_per_core):
                cpu_usage.labels(component=f"core_{i}").set(percent)
                
        except Exception as e:
            logger.error("Error collecting CPU metrics", error=str(e))
            
    def _collect_disk_metrics(self):
        """Collect disk usage and I/O metrics."""
        try:
            # Disk usage for key paths
            paths_to_monitor = {
                "/": "root",
                "/app": "app",
                "/tmp": "tmp"
            }
            
            for path, label in paths_to_monitor.items():
                try:
                    usage = psutil.disk_usage(path)
                    disk_usage.labels(path=label, type="total").set(usage.total)
                    disk_usage.labels(path=label, type="used").set(usage.used)
                    disk_usage.labels(path=label, type="free").set(usage.free)
                except PermissionError:
                    pass
                    
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io and self._last_disk_io:
                read_diff = disk_io.read_count - self._last_disk_io.read_count
                write_diff = disk_io.write_count - self._last_disk_io.write_count
                
                if read_diff > 0:
                    disk_io_operations.labels(
                        operation="read", disk="all"
                    ).inc(read_diff)
                if write_diff > 0:
                    disk_io_operations.labels(
                        operation="write", disk="all"
                    ).inc(write_diff)
                    
            self._last_disk_io = disk_io
            
        except Exception as e:
            logger.error("Error collecting disk metrics", error=str(e))
            
    def _collect_network_metrics(self):
        """Collect network I/O metrics."""
        try:
            net_io = psutil.net_io_counters(pernic=True)
            
            for interface, stats in net_io.items():
                if interface == 'lo':  # Skip loopback
                    continue
                    
                if self._last_net_io and interface in self._last_net_io:
                    last_stats = self._last_net_io[interface]
                    
                    bytes_sent_diff = stats.bytes_sent - last_stats.bytes_sent
                    bytes_recv_diff = stats.bytes_recv - last_stats.bytes_recv
                    
                    if bytes_sent_diff > 0:
                        network_bytes.labels(
                            interface=interface, direction="sent"
                        ).inc(bytes_sent_diff)
                    if bytes_recv_diff > 0:
                        network_bytes.labels(
                            interface=interface, direction="received"
                        ).inc(bytes_recv_diff)
                        
            self._last_net_io = net_io
            
        except Exception as e:
            logger.error("Error collecting network metrics", error=str(e))
            
    def _collect_thread_metrics(self):
        """Collect thread metrics."""
        try:
            threads = self._process.threads()
            thread_count.labels(state="total").set(len(threads))
            
            # Count threads by state if possible
            import threading
            active_threads = threading.active_count()
            thread_count.labels(state="active").set(active_threads)
            
            # Daemon threads
            daemon_count = sum(1 for t in threading.enumerate() if t.daemon)
            thread_count.labels(state="daemon").set(daemon_count)
            
        except Exception as e:
            logger.error("Error collecting thread metrics", error=str(e))
            
    def _collect_fd_metrics(self):
        """Collect file descriptor metrics."""
        try:
            # Open file descriptors
            open_files = self._process.open_files()
            open_file_descriptors.labels(type="files").set(len(open_files))
            
            # Connections (sockets)
            connections = self._process.connections()
            open_file_descriptors.labels(type="sockets").set(len(connections))
            
            # Total FDs
            num_fds = self._process.num_fds()
            open_file_descriptors.labels(type="total").set(num_fds)
            
        except Exception as e:
            logger.error("Error collecting file descriptor metrics", error=str(e))
            
    def _collect_connection_pool_metrics(self):
        """Collect connection pool metrics from various sources."""
        try:
            # Redis connection pool metrics
            # This would need to be integrated with actual Redis pool
            # For now, we'll set placeholder values
            
            # PostgreSQL connection pool metrics
            # This would need to be integrated with actual DB pool
            
            # The actual implementation would query the connection pools
            # Example:
            # redis_pool = get_redis_pool()
            # connection_pool_size.labels(pool="redis").set(redis_pool.max_connections)
            # connection_pool_active.labels(pool="redis").set(redis_pool.active_connections)
            
            pass
            
        except Exception as e:
            logger.error("Error collecting connection pool metrics", error=str(e))


# Global instance
_resource_monitor: Optional[ResourceMonitor] = None


async def start_resource_monitoring(interval: int = 10):
    """Start the global resource monitor."""
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = ResourceMonitor(interval=interval)
        await _resource_monitor.start()
    return _resource_monitor


async def stop_resource_monitoring():
    """Stop the global resource monitor."""
    global _resource_monitor
    if _resource_monitor:
        await _resource_monitor.stop()
        _resource_monitor = None