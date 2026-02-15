"""
Error rate monitoring and alerting for Tentackl.

Provides error rate calculations, thresholds, and alerting mechanisms.
"""

import asyncio
import time
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import structlog
from collections import defaultdict, deque

from .metrics import (
    MetricsCollector,
    errors_total,
    agent_executions,
    event_bus_messages,
    db_operations,
    redis_operations,
    Gauge
)

logger = structlog.get_logger()

# Error rate metrics
error_rate_1m = Gauge(
    'tentackl_error_rate_1m',
    'Error rate over the last minute',
    ['context', 'error_type']
)

error_rate_5m = Gauge(
    'tentackl_error_rate_5m',
    'Error rate over the last 5 minutes',
    ['context', 'error_type']
)

error_rate_15m = Gauge(
    'tentackl_error_rate_15m',
    'Error rate over the last 15 minutes',
    ['context', 'error_type']
)

alert_status = Gauge(
    'tentackl_alert_active',
    'Whether an alert is currently active',
    ['alert_name', 'severity']
)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(str, Enum):
    """Alert state."""
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class Alert:
    """Represents an alert."""
    name: str
    severity: AlertSeverity
    threshold: float
    window_minutes: int
    context: str
    error_type: Optional[str] = None
    cooldown_minutes: int = 5
    
    # Runtime state
    state: AlertState = AlertState.RESOLVED
    last_fired: Optional[datetime] = None
    last_value: float = 0.0
    consecutive_breaches: int = 0
    required_breaches: int = 1


@dataclass
class ErrorWindow:
    """Tracks errors within a time window."""
    window_size: timedelta
    errors: deque = field(default_factory=deque)
    total_requests: deque = field(default_factory=deque)
    
    def add_error(self, timestamp: float = None):
        """Add an error to the window."""
        if timestamp is None:
            timestamp = time.time()
        self.errors.append(timestamp)
        self._cleanup(timestamp)
        
    def add_request(self, timestamp: float = None):
        """Add a request to the window."""
        if timestamp is None:
            timestamp = time.time()
        self.total_requests.append(timestamp)
        self._cleanup(timestamp)
        
    def get_error_rate(self) -> float:
        """Calculate current error rate."""
        now = time.time()
        self._cleanup(now)
        
        if not self.total_requests:
            return 0.0
            
        error_count = len(self.errors)
        total_count = len(self.total_requests)
        
        return (error_count / total_count) * 100 if total_count > 0 else 0.0
        
    def get_error_count(self) -> int:
        """Get current error count."""
        self._cleanup(time.time())
        return len(self.errors)
        
    def _cleanup(self, current_time: float):
        """Remove old entries outside the window."""
        cutoff = current_time - self.window_size.total_seconds()
        
        while self.errors and self.errors[0] < cutoff:
            self.errors.popleft()
            
        while self.total_requests and self.total_requests[0] < cutoff:
            self.total_requests.popleft()


class ErrorMonitor:
    """Monitor error rates and trigger alerts."""
    
    def __init__(self, check_interval: int = 10):
        """
        Initialize error monitor.
        
        Args:
            check_interval: How often to check error rates (seconds)
        """
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Error windows by context and type
        self._windows: Dict[tuple, Dict[int, ErrorWindow]] = defaultdict(
            lambda: {
                1: ErrorWindow(timedelta(minutes=1)),
                5: ErrorWindow(timedelta(minutes=5)),
                15: ErrorWindow(timedelta(minutes=15))
            }
        )
        
        # Configured alerts
        self.alerts: List[Alert] = []
        
        # Alert callbacks
        self._alert_callbacks: List[Callable[[Alert, AlertState], None]] = []
        
        # Initialize default alerts
        self._setup_default_alerts()
        
    def _setup_default_alerts(self):
        """Configure default alerts."""
        # Agent execution alerts
        self.add_alert(Alert(
            name="high_agent_failure_rate_1m",
            severity=AlertSeverity.WARNING,
            threshold=10.0,  # 10% error rate
            window_minutes=1,
            context="agent",
            required_breaches=2
        ))
        
        self.add_alert(Alert(
            name="high_agent_failure_rate_5m",
            severity=AlertSeverity.ERROR,
            threshold=5.0,  # 5% error rate
            window_minutes=5,
            context="agent",
            required_breaches=1
        ))
        
        # Database operation alerts
        self.add_alert(Alert(
            name="high_db_error_rate",
            severity=AlertSeverity.CRITICAL,
            threshold=1.0,  # 1% error rate
            window_minutes=5,
            context="database",
            cooldown_minutes=10
        ))
        
        # Redis operation alerts
        self.add_alert(Alert(
            name="redis_connection_failures",
            severity=AlertSeverity.ERROR,
            threshold=5.0,  # 5% error rate
            window_minutes=1,
            context="redis",
            error_type="connection_error"
        ))
        
        # Event bus alerts
        self.add_alert(Alert(
            name="event_processing_failures",
            severity=AlertSeverity.WARNING,
            threshold=2.0,  # 2% error rate
            window_minutes=5,
            context="event_bus"
        ))
        
        # Generic high error rate
        self.add_alert(Alert(
            name="very_high_error_rate",
            severity=AlertSeverity.CRITICAL,
            threshold=20.0,  # 20% error rate
            window_minutes=1,
            context="system",
            required_breaches=3
        ))
        
    def add_alert(self, alert: Alert):
        """Add an alert configuration."""
        self.alerts.append(alert)
        logger.info("Alert configured", 
                   alert_name=alert.name,
                   severity=alert.severity,
                   threshold=alert.threshold)
        
    def add_alert_callback(self, callback: Callable[[Alert, AlertState], None]):
        """Add a callback for alert state changes."""
        self._alert_callbacks.append(callback)
        
    def track_error(self, context: str, error_type: str = "generic", 
                   error_details: Dict[str, Any] = None):
        """Track an error occurrence."""
        key = (context, error_type)
        timestamp = time.time()
        
        # Add to all windows
        for window in self._windows[key].values():
            window.add_error(timestamp)
            
        # Also track as system error
        if context != "system":
            system_key = ("system", "all")
            for window in self._windows[system_key].values():
                window.add_error(timestamp)
                
        # Update Prometheus metric
        MetricsCollector.track_error(error_type, error_details or {})
        
    def track_request(self, context: str, error_type: str = "generic"):
        """Track a request (successful or not)."""
        key = (context, error_type)
        timestamp = time.time()
        
        # Add to all windows
        for window in self._windows[key].values():
            window.add_request(timestamp)
            
        # Also track as system request
        if context != "system":
            system_key = ("system", "all")
            for window in self._windows[system_key].values():
                window.add_request(timestamp)
                
    async def start(self):
        """Start monitoring error rates."""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Error monitor started", check_interval=self.check_interval)
        
    async def stop(self):
        """Stop monitoring error rates."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Error monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_error_rates()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error("Error checking error rates", error=str(e))
                await asyncio.sleep(self.check_interval)
                
    async def _check_error_rates(self):
        """Check error rates and trigger alerts."""
        # Update error rate metrics
        self._update_error_rate_metrics()
        
        # Check alerts
        for alert in self.alerts:
            await self._check_alert(alert)
            
    def _update_error_rate_metrics(self):
        """Update Prometheus error rate metrics."""
        # Collect all contexts
        contexts = set()
        for key in self._windows.keys():
            context, error_type = key
            contexts.add((context, error_type))
            
        # Update metrics for each context
        for context, error_type in contexts:
            key = (context, error_type)
            windows = self._windows[key]
            
            # 1 minute rate
            if 1 in windows:
                rate = windows[1].get_error_rate()
                error_rate_1m.labels(context=context, error_type=error_type).set(rate)
                
            # 5 minute rate
            if 5 in windows:
                rate = windows[5].get_error_rate()
                error_rate_5m.labels(context=context, error_type=error_type).set(rate)
                
            # 15 minute rate
            if 15 in windows:
                rate = windows[15].get_error_rate()
                error_rate_15m.labels(context=context, error_type=error_type).set(rate)
                
    async def _check_alert(self, alert: Alert):
        """Check if an alert should be triggered."""
        # Get error rate for the alert's window
        key = (alert.context, alert.error_type or "generic")
        if key not in self._windows or alert.window_minutes not in self._windows[key]:
            return
            
        window = self._windows[key][alert.window_minutes]
        error_rate = window.get_error_rate()
        alert.last_value = error_rate
        
        # Check if in cooldown
        if alert.last_fired:
            cooldown_end = alert.last_fired + timedelta(minutes=alert.cooldown_minutes)
            if datetime.now() < cooldown_end:
                return
                
        # Check threshold
        if error_rate >= alert.threshold:
            alert.consecutive_breaches += 1
            
            if alert.consecutive_breaches >= alert.required_breaches:
                if alert.state != AlertState.FIRING:
                    await self._fire_alert(alert)
        else:
            if alert.state == AlertState.FIRING:
                await self._resolve_alert(alert)
            alert.consecutive_breaches = 0
            
    async def _fire_alert(self, alert: Alert):
        """Fire an alert."""
        alert.state = AlertState.FIRING
        alert.last_fired = datetime.now()
        
        # Update metric
        alert_status.labels(
            alert_name=alert.name,
            severity=alert.severity
        ).set(1)
        
        logger.warning("Alert fired",
                      alert_name=alert.name,
                      severity=alert.severity,
                      threshold=alert.threshold,
                      current_value=alert.last_value,
                      context=alert.context)
        
        # Call callbacks
        for callback in self._alert_callbacks:
            try:
                await asyncio.create_task(
                    asyncio.coroutine(callback)(alert, AlertState.FIRING)
                )
            except Exception as e:
                logger.error("Error in alert callback", error=str(e))
                
    async def _resolve_alert(self, alert: Alert):
        """Resolve an alert."""
        alert.state = AlertState.RESOLVED
        
        # Update metric
        alert_status.labels(
            alert_name=alert.name,
            severity=alert.severity
        ).set(0)
        
        logger.info("Alert resolved",
                   alert_name=alert.name,
                   severity=alert.severity,
                   current_value=alert.last_value)
        
        # Call callbacks
        for callback in self._alert_callbacks:
            try:
                await asyncio.create_task(
                    asyncio.coroutine(callback)(alert, AlertState.RESOLVED)
                )
            except Exception as e:
                logger.error("Error in alert callback", error=str(e))
                
    def get_current_error_rates(self) -> Dict[str, Dict[str, float]]:
        """Get current error rates for all contexts."""
        rates = {}
        
        for key, windows in self._windows.items():
            context, error_type = key
            context_key = f"{context}:{error_type}"
            
            rates[context_key] = {
                "1m": windows[1].get_error_rate() if 1 in windows else 0.0,
                "5m": windows[5].get_error_rate() if 5 in windows else 0.0,
                "15m": windows[15].get_error_rate() if 15 in windows else 0.0,
                "1m_count": windows[1].get_error_count() if 1 in windows else 0,
                "5m_count": windows[5].get_error_count() if 5 in windows else 0,
                "15m_count": windows[15].get_error_count() if 15 in windows else 0
            }
            
        return rates
        
    def get_active_alerts(self) -> List[Alert]:
        """Get currently active alerts."""
        return [alert for alert in self.alerts if alert.state == AlertState.FIRING]


# Global instance
_error_monitor: Optional[ErrorMonitor] = None


async def start_error_monitoring(check_interval: int = 10) -> ErrorMonitor:
    """Start the global error monitor."""
    global _error_monitor
    if _error_monitor is None:
        _error_monitor = ErrorMonitor(check_interval=check_interval)
        await _error_monitor.start()
    return _error_monitor


async def stop_error_monitoring():
    """Stop the global error monitor."""
    global _error_monitor
    if _error_monitor:
        await _error_monitor.stop()
        _error_monitor = None


def get_error_monitor() -> Optional[ErrorMonitor]:
    """Get the global error monitor instance."""
    return _error_monitor


# Decorator for tracking errors
def track_errors(context: str):
    """Decorator to automatically track errors in functions."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            monitor = get_error_monitor()
            if monitor:
                monitor.track_request(context)
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                if monitor:
                    error_type = type(e).__name__.lower()
                    monitor.track_error(context, error_type, {
                        "function": func.__name__,
                        "error": str(e)
                    })
                raise
                
        def sync_wrapper(*args, **kwargs):
            monitor = get_error_monitor()
            if monitor:
                monitor.track_request(context)
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if monitor:
                    error_type = type(e).__name__.lower()
                    monitor.track_error(context, error_type, {
                        "function": func.__name__,
                        "error": str(e)
                    })
                raise
                
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator