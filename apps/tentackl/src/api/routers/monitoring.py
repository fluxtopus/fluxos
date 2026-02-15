"""
# REVIEW:
# - Monitoring/alert configuration appears in-memory only; changes likely lost on restart.
API endpoints for monitoring, alerts, and error tracking.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from datetime import datetime

from src.monitoring.error_monitor import (
    get_error_monitor, 
    AlertSeverity, 
    Alert, 
    AlertState
)
from src.monitoring.alert_manager import (
    get_alert_manager,
    NotificationChannel,
    NotificationConfig
)
from src.api.auth_middleware import auth_middleware, AuthUser

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"]
)


class ErrorRateResponse(BaseModel):
    """Error rate information."""
    context: str
    error_type: str
    rate_1m: float = Field(description="Error rate over last 1 minute (%)")
    rate_5m: float = Field(description="Error rate over last 5 minutes (%)")
    rate_15m: float = Field(description="Error rate over last 15 minutes (%)")
    count_1m: int = Field(description="Error count over last 1 minute")
    count_5m: int = Field(description="Error count over last 5 minutes")
    count_15m: int = Field(description="Error count over last 15 minutes")


class AlertResponse(BaseModel):
    """Alert information."""
    name: str
    severity: AlertSeverity
    state: AlertState
    threshold: float
    current_value: float
    context: str
    error_type: Optional[str] = None
    window_minutes: int
    last_fired: Optional[datetime] = None


class NotificationChannelRequest(BaseModel):
    """Request to add/update notification channel."""
    channel: NotificationChannel
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    min_severity: AlertSeverity = AlertSeverity.WARNING
    contexts: Optional[List[str]] = None
    max_notifications_per_hour: int = 10
    aggregation_window_seconds: int = 300


class NotificationChannelResponse(BaseModel):
    """Notification channel information."""
    name: str
    channel: NotificationChannel
    enabled: bool
    min_severity: AlertSeverity
    contexts: Optional[List[str]]


class AlertConfigRequest(BaseModel):
    """Request to configure a new alert."""
    name: str
    severity: AlertSeverity
    threshold: float = Field(ge=0, le=100, description="Error rate threshold (%)")
    window_minutes: int = Field(ge=1, le=60)
    context: str
    error_type: Optional[str] = None
    cooldown_minutes: int = Field(default=5, ge=1)
    required_breaches: int = Field(default=1, ge=1)


@router.get("/error-rates", response_model=List[ErrorRateResponse])
async def get_error_rates(
    context: Optional[str] = None,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "view"))
):
    """Get current error rates across all contexts."""
    monitor = get_error_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="Error monitoring not available")
    
    rates = monitor.get_current_error_rates()
    
    result = []
    for key, values in rates.items():
        ctx, err_type = key.split(':', 1)
        
        # Filter by context if specified
        if context and ctx != context:
            continue
            
        result.append(ErrorRateResponse(
            context=ctx,
            error_type=err_type,
            rate_1m=values["1m"],
            rate_5m=values["5m"],
            rate_15m=values["15m"],
            count_1m=values["1m_count"],
            count_5m=values["5m_count"],
            count_15m=values["15m_count"]
        ))
    
    # Sort by highest 1-minute rate
    result.sort(key=lambda x: x.rate_1m, reverse=True)
    
    return result


@router.get("/alerts", response_model=List[AlertResponse])
async def get_configured_alerts(
    active_only: bool = False,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "view"))
):
    """Get all configured alerts or only active ones."""
    monitor = get_error_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="Error monitoring not available")
    
    if active_only:
        alerts = monitor.get_active_alerts()
    else:
        alerts = monitor.alerts
    
    return [
        AlertResponse(
            name=alert.name,
            severity=alert.severity,
            state=alert.state,
            threshold=alert.threshold,
            current_value=alert.last_value,
            context=alert.context,
            error_type=alert.error_type,
            window_minutes=alert.window_minutes,
            last_fired=alert.last_fired
        )
        for alert in alerts
    ]


@router.post("/alerts", response_model=dict)
async def configure_alert(
    request: AlertConfigRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "admin"))
):
    """Configure a new alert."""
    monitor = get_error_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="Error monitoring not available")
    
    # Create alert
    alert = Alert(
        name=request.name,
        severity=request.severity,
        threshold=request.threshold,
        window_minutes=request.window_minutes,
        context=request.context,
        error_type=request.error_type,
        cooldown_minutes=request.cooldown_minutes,
        required_breaches=request.required_breaches
    )
    
    monitor.add_alert(alert)
    
    return {
        "message": f"Alert '{request.name}' configured successfully",
        "alert": request.name
    }


@router.delete("/alerts/{alert_name}", response_model=dict)
async def remove_alert(
    alert_name: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "admin"))
):
    """Remove a configured alert."""
    monitor = get_error_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="Error monitoring not available")
    
    # Find and remove alert
    found = False
    for i, alert in enumerate(monitor.alerts):
        if alert.name == alert_name:
            monitor.alerts.pop(i)
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_name}' not found")
    
    return {"message": f"Alert '{alert_name}' removed successfully"}


@router.get("/notification-channels", response_model=List[NotificationChannelResponse])
async def get_notification_channels(
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "view"))
):
    """Get all configured notification channels."""
    manager = get_alert_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Alert management not available")
    
    return [
        NotificationChannelResponse(
            name=name,
            channel=config.channel,
            enabled=config.enabled,
            min_severity=config.min_severity,
            contexts=list(config.contexts) if config.contexts else None
        )
        for name, config in manager.channels.items()
    ]


@router.post("/notification-channels/{channel_name}", response_model=dict)
async def configure_notification_channel(
    channel_name: str,
    request: NotificationChannelRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "admin"))
):
    """Configure a notification channel."""
    manager = get_alert_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Alert management not available")
    
    # Validate channel configuration
    if request.channel == NotificationChannel.EMAIL:
        if not request.config.get("smtp_host") or not request.config.get("recipients"):
            raise HTTPException(
                status_code=400, 
                detail="Email channel requires 'smtp_host' and 'recipients' in config"
            )
    elif request.channel == NotificationChannel.SLACK:
        if not request.config.get("webhook_url"):
            raise HTTPException(
                status_code=400,
                detail="Slack channel requires 'webhook_url' in config"
            )
    elif request.channel == NotificationChannel.WEBHOOK:
        if not request.config.get("url"):
            raise HTTPException(
                status_code=400,
                detail="Webhook channel requires 'url' in config"
            )
    elif request.channel == NotificationChannel.PAGERDUTY:
        if not request.config.get("integration_key"):
            raise HTTPException(
                status_code=400,
                detail="PagerDuty channel requires 'integration_key' in config"
            )
    
    # Create notification config
    config = NotificationConfig(
        channel=request.channel,
        enabled=request.enabled,
        config=request.config,
        min_severity=request.min_severity,
        contexts=set(request.contexts) if request.contexts else None,
        max_notifications_per_hour=request.max_notifications_per_hour,
        aggregation_window_seconds=request.aggregation_window_seconds
    )
    
    manager.add_channel(channel_name, config)
    
    return {
        "message": f"Notification channel '{channel_name}' configured successfully",
        "channel": channel_name
    }


@router.delete("/notification-channels/{channel_name}", response_model=dict)
async def remove_notification_channel(
    channel_name: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "admin"))
):
    """Remove a notification channel."""
    manager = get_alert_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Alert management not available")
    
    if channel_name not in manager.channels:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")
    
    # Don't allow removing the log channel
    if channel_name == "log":
        raise HTTPException(status_code=400, detail="Cannot remove the default log channel")
    
    del manager.channels[channel_name]
    
    return {"message": f"Notification channel '{channel_name}' removed successfully"}


@router.post("/test-alert", response_model=dict)
async def test_alert(
    severity: AlertSeverity = AlertSeverity.WARNING,
    current_user: AuthUser = Depends(auth_middleware.require_permission("metrics", "admin"))
):
    """Trigger a test alert to verify notification channels."""
    manager = get_alert_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Alert management not available")
    
    # Create a test alert
    test_alert = Alert(
        name="test_alert",
        severity=severity,
        threshold=50.0,
        window_minutes=5,
        context="test",
        error_type="manual_test"
    )
    test_alert.state = AlertState.FIRING
    test_alert.last_value = 75.0
    test_alert.last_fired = datetime.now()
    
    # Send to all channels
    await manager.handle_alert(test_alert, AlertState.FIRING)
    
    # Get configured channels
    active_channels = [
        name for name, config in manager.channels.items() 
        if config.enabled
    ]
    
    return {
        "message": "Test alert sent",
        "severity": severity,
        "channels": active_channels
    }
