"""Generic webhook notification provider"""
# REVIEW:
# - Supports only POST/PUT; no retry/backoff, and response truncation may hide error context.

from typing import Any, Dict
import httpx
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult

class WebhookProvider(NotificationProviderInterface):
    """Generic webhook provider for custom integrations"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize webhook provider with credentials from context.
        
        Expected credentials:
        - webhook_url: Webhook URL to POST to
        - headers: Optional custom headers (dict)
        - method: HTTP method (default: POST)
        """
        self.webhook_url = credentials.get("webhook_url")
        self.headers = credentials.get("headers", {})
        self.method = credentials.get("method", "POST").upper()
        
        if not self.webhook_url:
            raise ValueError("Webhook provider requires 'webhook_url' in credentials")
    
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send notification via webhook"""
        # Build payload - can be customized via metadata
        payload = kwargs.get("payload", {
            "recipient": recipient,
            "content": content,
            **kwargs
        })
        
        # Default headers
        headers = {
            "Content-Type": "application/json",
            **self.headers
        }
        
        # Add custom headers from metadata
        if kwargs.get("headers"):
            headers.update(kwargs["headers"])
        
        try:
            async with httpx.AsyncClient(timeout=kwargs.get("timeout", 10.0)) as client:
                if self.method == "POST":
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        headers=headers
                    )
                elif self.method == "PUT":
                    response = await client.put(
                        self.webhook_url,
                        json=payload,
                        headers=headers
                    )
                else:
                    return NotificationResult(
                        success=False,
                        provider="webhook",
                        error=f"Unsupported HTTP method: {self.method}"
                    )
                
                # Accept any 2xx status code as success
                if 200 <= response.status_code < 300:
                    return NotificationResult(
                        success=True,
                        provider="webhook",
                        message_id=str(response.status_code),
                        metadata={
                            "status_code": response.status_code,
                            "response": response.text[:200]  # First 200 chars
                        }
                    )
                else:
                    return NotificationResult(
                        success=False,
                        provider="webhook",
                        error=f"Webhook returned {response.status_code}: {response.text[:200]}"
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                provider="webhook",
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate webhook provider configuration"""
        return "webhook_url" in config
