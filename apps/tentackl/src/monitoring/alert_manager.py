"""
Alert management and notification routing for Tentackl.

Handles alert aggregation, routing, and notification delivery.
"""

import asyncio
import json
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import structlog
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from .error_monitor import Alert, AlertState, AlertSeverity

logger = structlog.get_logger()


class NotificationChannel(str, Enum):
    """Notification channel types."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    LOG = "log"


@dataclass
class NotificationConfig:
    """Configuration for a notification channel."""
    channel: NotificationChannel
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Filtering
    min_severity: AlertSeverity = AlertSeverity.WARNING
    contexts: Optional[Set[str]] = None  # None means all contexts
    
    # Rate limiting
    max_notifications_per_hour: int = 10
    aggregation_window_seconds: int = 300  # 5 minutes


@dataclass
class NotificationEvent:
    """A notification event to be sent."""
    alert: Alert
    state: AlertState
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_name": self.alert.name,
            "severity": self.alert.severity,
            "state": self.state,
            "threshold": self.alert.threshold,
            "current_value": self.alert.last_value,
            "context": self.alert.context,
            "error_type": self.alert.error_type,
            "timestamp": self.timestamp.isoformat(),
            "details": self.context
        }


class AlertManager:
    """Manages alert routing and notifications."""
    
    def __init__(self):
        """Initialize alert manager."""
        self.channels: Dict[str, NotificationConfig] = {}
        self._notification_history: Dict[str, List[datetime]] = {}
        self._aggregation_buffer: Dict[str, List[NotificationEvent]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Setup default channels
        self._setup_default_channels()
        
    def _setup_default_channels(self):
        """Configure default notification channels."""
        # Log channel (always enabled)
        self.add_channel("log", NotificationConfig(
            channel=NotificationChannel.LOG,
            enabled=True,
            min_severity=AlertSeverity.INFO
        ))
        
    def add_channel(self, name: str, config: NotificationConfig):
        """Add a notification channel."""
        self.channels[name] = config
        logger.info("Notification channel added",
                   channel_name=name,
                   channel_type=config.channel,
                   enabled=config.enabled)
        
    async def start(self):
        """Start the alert manager."""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Alert manager started")
        
    async def stop(self):
        """Stop the alert manager."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
        # Send any remaining buffered notifications
        await self._flush_buffers()
        logger.info("Alert manager stopped")
        
    async def handle_alert(self, alert: Alert, state: AlertState):
        """Handle an alert state change."""
        event = NotificationEvent(alert=alert, state=state)
        
        # Check which channels should receive this notification
        for name, config in self.channels.items():
            if not config.enabled:
                continue
                
            # Check severity
            severity_levels = [AlertSeverity.INFO, AlertSeverity.WARNING, 
                             AlertSeverity.ERROR, AlertSeverity.CRITICAL]
            min_level_idx = severity_levels.index(config.min_severity)
            alert_level_idx = severity_levels.index(alert.severity)
            
            if alert_level_idx < min_level_idx:
                continue
                
            # Check context filter
            if config.contexts and alert.context not in config.contexts:
                continue
                
            # Check rate limit
            if not self._check_rate_limit(name, config):
                logger.warning("Rate limit exceeded for channel",
                             channel=name,
                             alert=alert.name)
                continue
                
            # Add to aggregation buffer
            buffer_key = f"{name}:{alert.severity}"
            if buffer_key not in self._aggregation_buffer:
                self._aggregation_buffer[buffer_key] = []
            self._aggregation_buffer[buffer_key].append(event)
            
    def _check_rate_limit(self, channel_name: str, config: NotificationConfig) -> bool:
        """Check if we can send to this channel without exceeding rate limits."""
        now = datetime.now()
        history_key = channel_name
        
        # Clean old history
        if history_key in self._notification_history:
            cutoff = now - timedelta(hours=1)
            self._notification_history[history_key] = [
                ts for ts in self._notification_history[history_key]
                if ts > cutoff
            ]
        else:
            self._notification_history[history_key] = []
            
        # Check count
        return len(self._notification_history[history_key]) < config.max_notifications_per_hour
        
    async def _process_loop(self):
        """Process notification queue."""
        while self._running:
            try:
                await self._process_buffers()
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error("Error processing notifications", error=str(e))
                await asyncio.sleep(5)
                
    async def _process_buffers(self):
        """Process aggregation buffers."""
        now = datetime.now()
        to_process = []
        
        # Check which buffers are ready to send
        for buffer_key, events in list(self._aggregation_buffer.items()):
            if not events:
                continue
                
            channel_name = buffer_key.split(':')[0]
            if channel_name not in self.channels:
                continue
                
            config = self.channels[channel_name]
            oldest_event = min(events, key=lambda e: e.timestamp)
            
            # Check if aggregation window has passed
            if (now - oldest_event.timestamp).total_seconds() >= config.aggregation_window_seconds:
                to_process.append((channel_name, config, events[:]))
                self._aggregation_buffer[buffer_key] = []
                
        # Send notifications
        for channel_name, config, events in to_process:
            await self._send_notification(channel_name, config, events)
            
    async def _flush_buffers(self):
        """Flush all aggregation buffers."""
        for buffer_key, events in list(self._aggregation_buffer.items()):
            if not events:
                continue
                
            channel_name = buffer_key.split(':')[0]
            if channel_name in self.channels:
                config = self.channels[channel_name]
                await self._send_notification(channel_name, config, events)
                
        self._aggregation_buffer.clear()
        
    async def _send_notification(self, channel_name: str, config: NotificationConfig, 
                               events: List[NotificationEvent]):
        """Send notification to a channel."""
        if not events:
            return
            
        try:
            # Update rate limit history
            now = datetime.now()
            if channel_name not in self._notification_history:
                self._notification_history[channel_name] = []
            self._notification_history[channel_name].append(now)
            
            # Route to appropriate handler
            if config.channel == NotificationChannel.LOG:
                await self._send_log_notification(events)
            elif config.channel == NotificationChannel.EMAIL:
                await self._send_email_notification(config, events)
            elif config.channel == NotificationChannel.SLACK:
                await self._send_slack_notification(config, events)
            elif config.channel == NotificationChannel.WEBHOOK:
                await self._send_webhook_notification(config, events)
            elif config.channel == NotificationChannel.PAGERDUTY:
                await self._send_pagerduty_notification(config, events)
                
        except Exception as e:
            logger.error("Failed to send notification",
                        channel=channel_name,
                        error=str(e),
                        event_count=len(events))
            
    async def _send_log_notification(self, events: List[NotificationEvent]):
        """Send notification to logs."""
        if len(events) == 1:
            event = events[0]
            logger.warning("Alert notification",
                         alert_name=event.alert.name,
                         severity=event.alert.severity,
                         state=event.state,
                         value=event.alert.last_value,
                         threshold=event.alert.threshold)
        else:
            # Aggregate multiple events
            by_severity = {}
            for event in events:
                severity = event.alert.severity
                if severity not in by_severity:
                    by_severity[severity] = []
                by_severity[severity].append(event)
                
            logger.warning("Alert notification batch",
                         total_alerts=len(events),
                         by_severity={
                             sev: len(evts) for sev, evts in by_severity.items()
                         })
            
    async def _send_email_notification(self, config: NotificationConfig, 
                                     events: List[NotificationEvent]):
        """Send email notification."""
        if not config.config.get("smtp_host") or not config.config.get("recipients"):
            logger.warning("Email notification not configured properly")
            return
            
        # Build email content
        subject = self._build_email_subject(events)
        body = self._build_email_body(events)
        
        # Send email
        msg = MIMEMultipart()
        msg['From'] = config.config.get("from_address", "tentackl@alerts.local")
        msg['To'] = ', '.join(config.config["recipients"])
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        try:
            with smtplib.SMTP(config.config["smtp_host"], 
                             config.config.get("smtp_port", 587)) as server:
                if config.config.get("smtp_tls", True):
                    server.starttls()
                if config.config.get("smtp_user") and config.config.get("smtp_password"):
                    server.login(config.config["smtp_user"], config.config["smtp_password"])
                server.send_message(msg)
                
            logger.info("Email notification sent", 
                       recipients=config.config["recipients"],
                       alert_count=len(events))
        except Exception as e:
            logger.error("Failed to send email", error=str(e))
            
    async def _send_slack_notification(self, config: NotificationConfig, 
                                     events: List[NotificationEvent]):
        """Send Slack notification."""
        if not config.config.get("webhook_url"):
            logger.warning("Slack webhook URL not configured")
            return
            
        # Build Slack message
        blocks = self._build_slack_blocks(events)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.config["webhook_url"],
                json={"blocks": blocks}
            ) as response:
                if response.status != 200:
                    logger.error("Failed to send Slack notification",
                               status=response.status)
                else:
                    logger.info("Slack notification sent", alert_count=len(events))
                    
    async def _send_webhook_notification(self, config: NotificationConfig, 
                                       events: List[NotificationEvent]):
        """Send generic webhook notification."""
        if not config.config.get("url"):
            logger.warning("Webhook URL not configured")
            return
            
        payload = {
            "alerts": [event.to_dict() for event in events],
            "timestamp": datetime.now().isoformat(),
            "source": "tentackl"
        }
        
        headers = config.config.get("headers", {})
        headers['Content-Type'] = 'application/json'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.config["url"],
                json=payload,
                headers=headers
            ) as response:
                if response.status >= 400:
                    logger.error("Failed to send webhook notification",
                               status=response.status,
                               url=config.config["url"])
                else:
                    logger.info("Webhook notification sent", 
                              alert_count=len(events),
                              url=config.config["url"])
                    
    async def _send_pagerduty_notification(self, config: NotificationConfig, 
                                         events: List[NotificationEvent]):
        """Send PagerDuty notification."""
        if not config.config.get("integration_key"):
            logger.warning("PagerDuty integration key not configured")
            return
            
        # Group by severity
        critical_events = [e for e in events if e.alert.severity == AlertSeverity.CRITICAL]
        other_events = [e for e in events if e.alert.severity != AlertSeverity.CRITICAL]
        
        # Send critical alerts immediately
        for event in critical_events:
            await self._send_single_pagerduty_event(config, event, "trigger")
            
        # Aggregate other events
        if other_events:
            summary = f"Tentackl: {len(other_events)} alerts"
            custom_details = {
                "alerts": [event.to_dict() for event in other_events]
            }
            
            payload = {
                "routing_key": config.config["integration_key"],
                "event_action": "trigger",
                "payload": {
                    "summary": summary,
                    "source": "tentackl",
                    "severity": "warning",
                    "custom_details": custom_details
                }
            }
            
            await self._send_pagerduty_payload(payload)
            
    async def _send_single_pagerduty_event(self, config: NotificationConfig,
                                         event: NotificationEvent, action: str):
        """Send a single PagerDuty event."""
        severity_map = {
            AlertSeverity.CRITICAL: "critical",
            AlertSeverity.ERROR: "error",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.INFO: "info"
        }
        
        payload = {
            "routing_key": config.config["integration_key"],
            "event_action": action,
            "dedup_key": f"tentackl:{event.alert.name}",
            "payload": {
                "summary": f"{event.alert.name}: {event.alert.last_value:.1f}% error rate",
                "source": "tentackl",
                "severity": severity_map.get(event.alert.severity, "warning"),
                "custom_details": event.to_dict()
            }
        }
        
        await self._send_pagerduty_payload(payload)
        
    async def _send_pagerduty_payload(self, payload: Dict[str, Any]):
        """Send payload to PagerDuty."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            ) as response:
                if response.status != 202:
                    logger.error("Failed to send PagerDuty notification",
                               status=response.status)
                else:
                    logger.info("PagerDuty notification sent")
                    
    def _build_email_subject(self, events: List[NotificationEvent]) -> str:
        """Build email subject line."""
        if len(events) == 1:
            event = events[0]
            return f"[Tentackl Alert] {event.alert.severity.upper()}: {event.alert.name}"
        else:
            severities = set(e.alert.severity for e in events)
            highest = max(severities, key=lambda s: 
                         [AlertSeverity.INFO, AlertSeverity.WARNING, 
                          AlertSeverity.ERROR, AlertSeverity.CRITICAL].index(s))
            return f"[Tentackl Alert] {len(events)} alerts - Highest: {highest.upper()}"
            
    def _build_email_body(self, events: List[NotificationEvent]) -> str:
        """Build email body HTML."""
        html = """
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Tentackl Alert Notification</h2>
            <p>The following alerts have been triggered:</p>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Alert</th>
                    <th>Severity</th>
                    <th>State</th>
                    <th>Value</th>
                    <th>Threshold</th>
                    <th>Context</th>
                    <th>Time</th>
                </tr>
        """
        
        for event in events:
            html += f"""
                <tr>
                    <td>{event.alert.name}</td>
                    <td style="color: {self._get_severity_color(event.alert.severity)}">
                        {event.alert.severity.upper()}
                    </td>
                    <td>{event.state}</td>
                    <td>{event.alert.last_value:.2f}%</td>
                    <td>{event.alert.threshold}%</td>
                    <td>{event.alert.context}</td>
                    <td>{event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                </tr>
            """
            
        html += """
            </table>
            <p style="margin-top: 20px; font-size: 12px; color: #666;">
                This is an automated message from Tentackl monitoring system.
            </p>
        </body>
        </html>
        """
        
        return html
        
    def _build_slack_blocks(self, events: List[NotificationEvent]) -> List[Dict]:
        """Build Slack message blocks."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Tentackl Alert Notification"
                }
            }
        ]
        
        # Summary
        if len(events) == 1:
            event = events[0]
            color = self._get_severity_color(event.alert.severity)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event.alert.name}*\n"
                           f"Severity: *{event.alert.severity.upper()}*\n"
                           f"Current Value: *{event.alert.last_value:.2f}%*\n"
                           f"Threshold: *{event.alert.threshold}%*"
                }
            })
        else:
            severity_counts = {}
            for event in events:
                severity = event.alert.severity
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                
            summary = "Multiple alerts triggered:\n"
            for severity, count in severity_counts.items():
                summary += f"• {severity.upper()}: {count}\n"
                
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary
                }
            })
            
        # Add divider
        blocks.append({"type": "divider"})
        
        # Details for each alert (limit to 5 to avoid message size limits)
        for event in events[:5]:
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Alert:*\n{event.alert.name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Context:*\n{event.alert.context}"
                    }
                ]
            })
            
        if len(events) > 5:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_...and {len(events) - 5} more alerts_"
                }
            })
            
        return blocks
        
    def _get_severity_color(self, severity: AlertSeverity) -> str:
        """Get color for severity level."""
        colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ff9900",
            AlertSeverity.ERROR: "#ff0000",
            AlertSeverity.CRITICAL: "#990000"
        }
        return colors.get(severity, "#000000")


# Global instance
_alert_manager: Optional[AlertManager] = None


async def start_alert_manager() -> AlertManager:
    """Start the global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        await _alert_manager.start()
    return _alert_manager


async def stop_alert_manager():
    """Stop the global alert manager."""
    global _alert_manager
    if _alert_manager:
        await _alert_manager.stop()
        _alert_manager = None


def get_alert_manager() -> Optional[AlertManager]:
    """Get the global alert manager instance."""
    return _alert_manager