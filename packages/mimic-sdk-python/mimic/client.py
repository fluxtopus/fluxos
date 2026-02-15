"""Mimic Python SDK Client"""

import httpx
from typing import Optional, Dict, Any, List


class MimicClient:
    """Python client for Mimic Notification Service"""
    
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        """
        Initialize Mimic client.
        
        Args:
            api_key: Your Mimic API key
            base_url: Base URL of Mimic API (default: http://localhost:8000)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def send_notification(
        self,
        recipient: str,
        content: str,
        provider: str = "email",
        template_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        subject: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a notification.

        Args:
            recipient: Notification recipient
            content: Message content
            provider: Provider type (email, sms, slack, discord, telegram, webhook)
            template_id: Optional template ID
            metadata: Optional metadata dict
            subject: Email subject (convenience parameter, merged into metadata)
            from_name: Email sender display name (convenience parameter, merged into metadata)

        Returns:
            Delivery response with delivery_id and status
        """
        # Build metadata with explicit parameters taking precedence
        final_metadata = metadata.copy() if metadata else {}
        if subject is not None:
            final_metadata["subject"] = subject
        if from_name is not None:
            final_metadata["from_name"] = from_name

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/send",
                headers=self.headers,
                json={
                    "recipient": recipient,
                    "content": content,
                    "provider": provider,
                    "template_id": template_id,
                    "metadata": final_metadata
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def get_delivery_status(self, delivery_id: str) -> Dict[str, Any]:
        """
        Get delivery status.
        
        Args:
            delivery_id: Delivery ID from send_notification response
        
        Returns:
            Delivery status information
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/status/{delivery_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def create_provider_key(
        self,
        provider_type: str,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        from_email: Optional[str] = None,
        from_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a provider key (BYOK).
        
        Args:
            provider_type: Provider type (email, sms, slack, discord, telegram, webhook)
            api_key: API key (for email, sms)
            secret: Secret (for sms)
            webhook_url: Webhook URL (for slack, discord, webhook)
            bot_token: Bot token (for telegram)
            from_email: From email (for email)
            from_number: From number (for sms)
        
        Returns:
            Provider key information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/provider-keys",
                headers=self.headers,
                json={
                    "provider_type": provider_type,
                    "api_key": api_key,
                    "secret": secret,
                    "webhook_url": webhook_url,
                    "bot_token": bot_token,
                    "from_email": from_email,
                    "from_number": from_number
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def list_provider_keys(self) -> List[Dict[str, Any]]:
        """List all provider keys."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/provider-keys",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def test_provider_key(self, provider_type: str) -> Dict[str, Any]:
        """
        Test a provider key connection.
        
        Args:
            provider_type: Provider type to test
        
        Returns:
            Test result
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/provider-keys/{provider_type}/test",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def create_template(
        self,
        name: str,
        content: str,
        variables: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a message template.
        
        Args:
            name: Template name
            content: Template content (supports {{variable}} syntax)
            variables: List of variable names (auto-extracted if not provided)
        
        Returns:
            Template information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/templates",
                headers=self.headers,
                json={
                    "name": name,
                    "content": content,
                    "variables": variables
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def list_templates(self) -> List[Dict[str, Any]]:
        """List all templates."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/templates",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_delivery_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        provider: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get delivery logs.
        
        Args:
            limit: Number of results (max 100)
            offset: Pagination offset
            provider: Filter by provider
            status: Filter by status
        
        Returns:
            List of delivery logs
        """
        params = {"limit": limit, "offset": offset}
        if provider:
            params["provider"] = provider
        if status:
            params["status"] = status
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/logs",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
    
    async def get_analytics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get analytics.

        Args:
            days: Number of days to analyze

        Returns:
            Analytics data
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/analytics",
                headers=self.headers,
                params={"days": days}
            )
            response.raise_for_status()
            return response.json()

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        variables: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a notification using a system template.

        System templates are org-scoped or platform-wide templates for
        transactional emails (invitations, password resets, etc.).

        Args:
            recipient: Email recipient address
            template_name: Template name (e.g., "invitation", "welcome", "password_reset")
            variables: Dict of template variables to substitute (e.g., {"brand_name": "Acme"})
            metadata: Optional additional metadata (from_email, from_name)

        Returns:
            Delivery response with delivery_id and status
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/send-template",
                headers=self.headers,
                json={
                    "recipient": recipient,
                    "template_name": template_name,
                    "variables": variables,
                    "metadata": metadata,
                }
            )
            response.raise_for_status()
            return response.json()

