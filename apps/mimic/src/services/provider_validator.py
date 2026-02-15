"""Provider validation service for testing connections"""

import httpx
from typing import Optional

class ProviderValidatorService:
    """Service for validating provider API keys and connections"""
    
    async def validate_provider(
        self,
        provider_type: str,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        email_provider: Optional[str] = None
    ) -> bool:
        """Validate a provider connection"""
        if provider_type == "email":
            # Route to specific email provider validator
            if email_provider == "postmark":
                return await self._validate_postmark(api_key)
            elif email_provider == "resend":
                return await self._validate_resend(api_key)
            else:
                return await self._validate_sendgrid(api_key)
        elif provider_type == "sms":
            return await self._validate_twilio(api_key, secret)
        elif provider_type == "slack":
            return await self._validate_slack(webhook_url)
        elif provider_type == "discord":
            return await self._validate_discord(webhook_url)
        elif provider_type == "telegram":
            return await self._validate_telegram(bot_token)
        elif provider_type == "webhook":
            return await self._validate_webhook(webhook_url)
        else:
            return False
    
    async def _validate_sendgrid(self, api_key: Optional[str]) -> bool:
        """Validate SendGrid API key"""
        if not api_key:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.sendgrid.com/v3/user/profile",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False

    async def _validate_postmark(self, api_key: Optional[str]) -> bool:
        """Validate Postmark API key (Server Token)"""
        if not api_key:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.postmarkapp.com/server",
                    headers={
                        "X-Postmark-Server-Token": api_key,
                        "Accept": "application/json"
                    },
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False

    async def _validate_resend(self, api_key: Optional[str]) -> bool:
        """Validate Resend API key"""
        if not api_key:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.resend.com/domains",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                    },
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def _validate_twilio(self, api_key: Optional[str], secret: Optional[str]) -> bool:
        """Validate Twilio credentials"""
        if not api_key or not secret:
            return False
        try:
            # Twilio uses Account SID and Auth Token
            # Basic validation - check if credentials format is correct
            # In production, make actual API call to Twilio
            return len(api_key) > 0 and len(secret) > 0
        except Exception:
            return False
    
    async def _validate_slack(self, webhook_url: Optional[str]) -> bool:
        """Validate Slack webhook URL"""
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"text": "Test connection"},
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def _validate_discord(self, webhook_url: Optional[str]) -> bool:
        """Validate Discord webhook URL"""
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"content": "Test connection"},
                    timeout=5.0
                )
                return response.status_code in [200, 204]
        except Exception:
            return False
    
    async def _validate_telegram(self, bot_token: Optional[str]) -> bool:
        """Validate Telegram bot token"""
        if not bot_token:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe",
                    timeout=5.0
                )
                return response.status_code == 200 and response.json().get("ok", False)
        except Exception:
            return False
    
    async def _validate_webhook(self, webhook_url: Optional[str]) -> bool:
        """Validate generic webhook URL"""
        if not webhook_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"test": True},
                    timeout=5.0
                )
                # Accept any 2xx status code
                return 200 <= response.status_code < 300
        except Exception:
            return False

