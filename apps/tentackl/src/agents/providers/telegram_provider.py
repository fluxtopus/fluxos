"""Telegram notification provider (Bot API)"""
# REVIEW:
# - No retry or rate-limit handling; errors are surfaced as strings only.

from typing import Any, Dict
import httpx
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult

class TelegramProvider(NotificationProviderInterface):
    """Telegram provider using Bot API"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize Telegram provider with credentials from context.
        
        Expected credentials:
        - bot_token: Telegram bot token
        """
        self.bot_token = credentials.get("bot_token")
        
        if not self.bot_token:
            raise ValueError("Telegram provider requires 'bot_token' in credentials")
        
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send message to Telegram via Bot API"""
        # Recipient is chat_id (can be user ID or username)
        url = f"{self.api_url}/sendMessage"
        
        payload = {
            "chat_id": recipient,
            "text": content
        }
        
        # Add optional Telegram formatting
        if kwargs.get("parse_mode"):
            payload["parse_mode"] = kwargs["parse_mode"]  # HTML, Markdown, etc.
        if kwargs.get("disable_web_page_preview"):
            payload["disable_web_page_preview"] = kwargs["disable_web_page_preview"]
        if kwargs.get("reply_to_message_id"):
            payload["reply_to_message_id"] = kwargs["reply_to_message_id"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        message = result.get("result", {})
                        return NotificationResult(
                            success=True,
                            provider="telegram",
                            message_id=str(message.get("message_id", "")),
                            metadata={"chat_id": message.get("chat", {}).get("id")}
                        )
                    else:
                        return NotificationResult(
                            success=False,
                            provider="telegram",
                            error=result.get("description", "Unknown error")
                        )
                else:
                    error_text = response.text
                    return NotificationResult(
                        success=False,
                        provider="telegram",
                        error=f"Telegram API returned {response.status_code}: {error_text}"
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                provider="telegram",
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Telegram provider configuration"""
        return "bot_token" in config
