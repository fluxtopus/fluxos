"""Prometheus metrics for Tentackl monitoring."""

from typing import Optional, Dict, Any
from prometheus_client import Counter, Histogram, Gauge, Info
from functools import wraps
import time
import asyncio
from contextlib import contextmanager, asynccontextmanager


# Agent execution metrics
agent_executions = Counter(
    'tentackl_agent_executions_total',
    'Total number of agent executions',
    ['agent_type', 'agent_id', 'status']
)

agent_execution_duration = Histogram(
    'tentackl_agent_execution_seconds',
    'Agent execution duration in seconds',
    ['agent_type', 'agent_id'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

# Workflow metrics
workflow_active = Gauge(
    'tentackl_workflows_active',
    'Number of currently active workflows',
    ['workflow_status']
)

workflow_duration = Histogram(
    'tentackl_workflow_duration_seconds',
    'Workflow execution duration in seconds',
    ['workflow_type'],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0, 3600.0)
)

# Error metrics
errors_total = Counter(
    'tentackl_errors_total',
    'Total number of errors',
    ['error_type', 'component', 'severity']
)

# Event bus metrics
event_bus_messages = Counter(
    'tentackl_event_bus_messages_total',
    'Total number of event bus messages',
    ['event_type', 'source', 'status']
)

event_processing_duration = Histogram(
    'tentackl_event_processing_seconds',
    'Event processing duration in seconds',
    ['event_type'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
)

# Redis operations metrics
redis_operations = Counter(
    'tentackl_redis_operations_total',
    'Total number of Redis operations',
    ['operation', 'status']
)

redis_operation_duration = Histogram(
    'tentackl_redis_operation_seconds',
    'Redis operation duration in seconds',
    ['operation'],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5)
)

# Database operations metrics
db_operations = Counter(
    'tentackl_db_operations_total',
    'Total number of database operations',
    ['operation', 'table', 'status']
)

db_operation_duration = Histogram(
    'tentackl_db_operation_seconds',
    'Database operation duration in seconds',
    ['operation', 'table'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

# Resource usage metrics
memory_usage = Gauge(
    'tentackl_memory_usage_bytes',
    'Memory usage in bytes',
    ['component']
)

cpu_usage = Gauge(
    'tentackl_cpu_usage_percent',
    'CPU usage percentage',
    ['component']
)

# Connection pool metrics
connection_pool_size = Gauge(
    'tentackl_connection_pool_size',
    'Connection pool size',
    ['pool_type', 'pool_name']
)

connection_pool_active = Gauge(
    'tentackl_connection_pool_active',
    'Active connections in pool',
    ['pool_type', 'pool_name']
)

# System info
system_info = Info(
    'tentackl_system',
    'Tentackl system information'
)


class MetricsCollector:
    """Utility class for collecting metrics."""
    
    @staticmethod
    def track_agent_execution(agent_type: str, agent_id: str):
        """Decorator to track agent execution metrics."""
        def decorator(func):
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    start_time = time.time()
                    status = "success"
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as e:
                        status = "failure"
                        errors_total.labels(
                            error_type=type(e).__name__,
                            component="agent",
                            severity="error"
                        ).inc()
                        raise
                    finally:
                        duration = time.time() - start_time
                        agent_executions.labels(
                            agent_type=agent_type,
                            agent_id=agent_id,
                            status=status
                        ).inc()
                        agent_execution_duration.labels(
                            agent_type=agent_type,
                            agent_id=agent_id
                        ).observe(duration)
                return async_wrapper
            else:
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    start_time = time.time()
                    status = "success"
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception as e:
                        status = "failure"
                        errors_total.labels(
                            error_type=type(e).__name__,
                            component="agent",
                            severity="error"
                        ).inc()
                        raise
                    finally:
                        duration = time.time() - start_time
                        agent_executions.labels(
                            agent_type=agent_type,
                            agent_id=agent_id,
                            status=status
                        ).inc()
                        agent_execution_duration.labels(
                            agent_type=agent_type,
                            agent_id=agent_id
                        ).observe(duration)
                return sync_wrapper
        return decorator
    
    @staticmethod
    @contextmanager
    def track_redis_operation(operation: str):
        """Context manager to track Redis operations."""
        start_time = time.time()
        status = "success"
        try:
            yield
        except Exception as e:
            status = "failure"
            errors_total.labels(
                error_type=type(e).__name__,
                component="redis",
                severity="error"
            ).inc()
            raise
        finally:
            duration = time.time() - start_time
            redis_operations.labels(
                operation=operation,
                status=status
            ).inc()
            redis_operation_duration.labels(
                operation=operation
            ).observe(duration)
    
    @staticmethod
    @asynccontextmanager
    async def track_db_operation(operation: str, table: str):
        """Async context manager to track database operations."""
        start_time = time.time()
        status = "success"
        try:
            yield
        except Exception as e:
            status = "failure"
            errors_total.labels(
                error_type=type(e).__name__,
                component="database",
                severity="error"
            ).inc()
            raise
        finally:
            duration = time.time() - start_time
            db_operations.labels(
                operation=operation,
                table=table,
                status=status
            ).inc()
            db_operation_duration.labels(
                operation=operation,
                table=table
            ).observe(duration)
    
    @staticmethod
    def track_event(event_type: str, source: str, status: str = "processed"):
        """Track event bus messages."""
        event_bus_messages.labels(
            event_type=event_type,
            source=source,
            status=status
        ).inc()
    
    @staticmethod
    @contextmanager
    def track_event_processing(event_type: str):
        """Context manager to track event processing duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            event_processing_duration.labels(
                event_type=event_type
            ).observe(duration)

    @staticmethod
    @contextmanager
    def track_operation(operation: str):
        """Generic context manager to track an arbitrary operation.

        Records errors_total on exceptions; primarily used in workflow manager paths.
        """
        try:
            yield
        except Exception as e:
            errors_total.labels(
                error_type=type(e).__name__,
                component="operation",
                severity="error",
            ).inc()
            raise
    
    @staticmethod
    def update_workflow_count(status: str, delta: int):
        """Update active workflow count."""
        workflow_active.labels(workflow_status=status).inc(delta)
    
    @staticmethod
    def track_workflow_duration(workflow_type: str, duration: float):
        """Track workflow execution duration."""
        workflow_duration.labels(workflow_type=workflow_type).observe(duration)
    
    @staticmethod
    def update_memory_usage(component: str, bytes_used: int):
        """Update memory usage metric."""
        memory_usage.labels(component=component).set(bytes_used)
    
    @staticmethod
    def update_cpu_usage(component: str, percent: float):
        """Update CPU usage metric."""
        cpu_usage.labels(component=component).set(percent)
    
    @staticmethod
    def update_connection_pool_metrics(
        pool_type: str,
        pool_name: str,
        size: int,
        active: int
    ):
        """Update connection pool metrics."""
        connection_pool_size.labels(
            pool_type=pool_type,
            pool_name=pool_name
        ).set(size)
        connection_pool_active.labels(
            pool_type=pool_type,
            pool_name=pool_name
        ).set(active)
    
    @staticmethod
    def set_system_info(info: Dict[str, str]):
        """Set system information."""
        system_info.info(info)
