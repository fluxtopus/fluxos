# REVIEW:
# - Provider selection logic is hard-coded; no registry or plugin mechanism for extensibility.
# - Credentials passed through task payload; no validation beyond presence.
"""Notifier Agent - executes notification delivery via providers"""

from typing import Any, Dict
import structlog
from src.agents.base import Agent, AgentConfig, AgentStatus
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult
from src.agents.providers.sms_provider import SMSProvider
from src.agents.providers.slack_provider import SlackProvider
from src.agents.providers.discord_provider import DiscordProvider
from src.agents.providers.telegram_provider import TelegramProvider
from src.agents.providers.webhook_provider import WebhookProvider

logger = structlog.get_logger()


class NotifierAgent(Agent):
    """
    Agent responsible for delivering notifications via various providers.
    Accepts provider credentials from workflow context (BYOK support).
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._providers: Dict[str, NotificationProviderInterface] = {}
    
    def _get_provider(self, provider_type: str, credentials: Dict[str, Any]) -> NotificationProviderInterface:
        """Get or create a provider instance with credentials"""
        # Provider instances are created on-demand with credentials from context
        # This ensures BYOK - credentials come from workflow context, not hardcoded
        
        if provider_type == "email":
            raise ValueError("Email delivery is handled by the send_email plugin, not NotifierAgent")
        elif provider_type == "sms":
            return SMSProvider(credentials)
        elif provider_type == "slack":
            return SlackProvider(credentials)
        elif provider_type == "discord":
            return DiscordProvider(credentials)
        elif provider_type == "telegram":
            return TelegramProvider(credentials)
        elif provider_type == "webhook":
            return WebhookProvider(credentials)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute notification task.
        
        Expected task schema:
        {
            "provider": "email" | "sms" | "slack" | "discord" | "telegram" | "webhook",
            "recipient": "user_id_or_channel",
            "content": "Message content",
            "template_id": "optional_template_id",
            "metadata": {},
            "provider_credentials": {
                "api_key": "...",
                "secret": "...",
                "webhook_url": "...",
                "bot_token": "..."
            }
        }
        """
        provider_name = task.get("provider")
        recipient = task.get("recipient")
        content = task.get("content")
        provider_credentials = task.get("provider_credentials", {})
        
        if not all([provider_name, recipient, content]):
            raise ValueError("Missing required fields: provider, recipient, or content")
        
        logger.info(
            "Sending notification",
            provider=provider_name,
            recipient=recipient,
            agent_id=self.id
        )
        
        try:
            # Get provider instance with credentials from context
            provider = self._get_provider(provider_name, provider_credentials)
            
            # Execute the send operation
            result: NotificationResult = await provider.send(
                recipient=recipient,
                content=content,
                **task.get("metadata", {})
            )
            
            if not result.success:
                logger.error(
                    "Notification failed",
                    error=result.error,
                    provider=provider_name,
                    recipient=recipient
                )
                raise RuntimeError(f"Failed to send notification: {result.error}")
            
            logger.info(
                "Notification sent successfully",
                provider=provider_name,
                recipient=recipient,
                message_id=result.message_id
            )
            
            return result.model_dump()
        
        except Exception as e:
            logger.error(
                "Notification error",
                error=str(e),
                provider=provider_name,
                recipient=recipient
            )
            raise
