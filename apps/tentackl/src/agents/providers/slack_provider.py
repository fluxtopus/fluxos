"""Slack notification provider (Webhook)"""
# REVIEW:
# - No rate limit handling or retry; response text used as message_id is ambiguous ("ok").

from typing import Any, Dict
import httpx
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult

class SlackProvider(NotificationProviderInterface):
    """Slack provider using webhook URL"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize Slack provider with credentials from context.
        
        Expected credentials:
        - webhook_url: Slack webhook URL
        """
        self.webhook_url = credentials.get("webhook_url")
        
        if not self.webhook_url:
            raise ValueError("Slack provider requires 'webhook_url' in credentials")
    
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send message to Slack via webhook"""
        # Slack webhooks send to a channel, recipient can be channel name or webhook default
        payload = {
            "text": content,
            "channel": recipient if recipient.startswith("#") else f"#{recipient}"
        }
        
        # Add optional Slack formatting
        if kwargs.get("username"):
            payload["username"] = kwargs["username"]
        if kwargs.get("icon_emoji"):
            payload["icon_emoji"] = kwargs["icon_emoji"]
        if kwargs.get("blocks"):
            payload["blocks"] = kwargs["blocks"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload
                )
                
                if response.status_code == 200:
                    return NotificationResult(
                        success=True,
                        provider="slack",
                        message_id=response.text,  # Slack returns "ok" or timestamp
                        metadata={"status_code": response.status_code}
                    )
                else:
                    error_text = response.text
                    return NotificationResult(
                        success=False,
                        provider="slack",
                        error=f"Slack webhook returned {response.status_code}: {error_text}"
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                provider="slack",
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Slack provider configuration"""
        return "webhook_url" in config
