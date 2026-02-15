"""Discord notification provider (Webhook)"""
# REVIEW:
# - Uses httpx AsyncClient per send; no retry/backoff or rate-limit handling.

from typing import Any, Dict
import httpx
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult

class DiscordProvider(NotificationProviderInterface):
    """Discord provider using webhook URL"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize Discord provider with credentials from context.
        
        Expected credentials:
        - webhook_url: Discord webhook URL
        """
        self.webhook_url = credentials.get("webhook_url")
        
        if not self.webhook_url:
            raise ValueError("Discord provider requires 'webhook_url' in credentials")
    
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send message to Discord via webhook"""
        # Discord webhooks send to a channel, recipient is typically ignored (webhook is channel-specific)
        payload = {
            "content": content
        }
        
        # Add optional Discord formatting
        if kwargs.get("username"):
            payload["username"] = kwargs["username"]
        if kwargs.get("avatar_url"):
            payload["avatar_url"] = kwargs["avatar_url"]
        if kwargs.get("embeds"):
            payload["embeds"] = kwargs["embeds"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload
                )
                
                if response.status_code in [200, 204]:
                    result = response.json() if response.content else {}
                    return NotificationResult(
                        success=True,
                        provider="discord",
                        message_id=str(result.get("id", "")),
                        metadata={"status_code": response.status_code}
                    )
                else:
                    error_text = response.text
                    return NotificationResult(
                        success=False,
                        provider="discord",
                        error=f"Discord webhook returned {response.status_code}: {error_text}"
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                provider="discord",
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Discord provider configuration"""
        return "webhook_url" in config
