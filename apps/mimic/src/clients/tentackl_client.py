"""Tentackl integration client"""

import httpx
from typing import Dict, Any, Optional
from src.config import settings
from src.database.models import ProviderKey
from src.services.key_encryption import KeyEncryptionService
from src.database.database import SessionLocal
import structlog

logger = structlog.get_logger()
encryption_service = KeyEncryptionService()


class TentacklClient:
    """HTTP client for interacting with Tentackl workflow API"""
    
    def __init__(self):
        self.base_url = settings.TENTACKL_URL
        self.api_key = settings.TENTACKL_API_KEY
        self.timeout = 30.0
    
    async def send_notification(
        self,
        user_id: str,
        recipient: str,
        content: str,
        provider: str,
        template_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Send a notification via Tentackl workflow"""
        # Get user's provider keys
        db = SessionLocal()
        try:
            provider_key = db.query(ProviderKey).filter(
                ProviderKey.user_id == user_id,
                ProviderKey.provider_type == provider,
                ProviderKey.is_active == True
            ).first()
            
            if not provider_key:
                raise ValueError(f"No active provider key found for {provider}")
            
            # Decrypt provider credentials
            provider_credentials = self._get_provider_credentials(provider_key)
            
            # Prepare workflow parameters
            parameters = {
                "recipient": recipient,
                "content": content,
                "provider": provider,
                "template_id": template_id,
                "provider_credentials": provider_credentials,
                **(metadata or {})
            }
            
            # Get spec ID first, then use published workflow endpoint for auto-execution
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                # Get spec by name to get the spec_id
                spec_response = await client.get(
                    f"{self.base_url}/api/workflow-specs/name/notification_delivery_v1",
                    headers={"X-API-Key": self.api_key}
                )
                spec_response.raise_for_status()
                spec_data = spec_response.json()
                spec_id = spec_data.get("id")
                
                if not spec_id:
                    raise ValueError("Workflow spec 'notification_delivery_v1' not found")
                
                # Use the published workflow endpoint which creates execution tree and starts execution
                # (now supports "api" source after our update)
                response = await client.post(
                    f"{self.base_url}/api/workflows/published/{spec_id}/run",
                    json={
                        "parameters": parameters
                    },
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                # The published workflow endpoint returns {"ok": True, "run_id": "...", ...}
                run_id = data.get("run_id")
                if not run_id:
                    # Fallback to other possible fields
                    run_id = data.get("workflow_id") or data.get("id") or ""
                if not run_id:
                    logger.error("No run_id in response", response_data=data)
                    raise ValueError("Failed to get workflow run ID from Tentackl response")
                
                logger.info("Created and started workflow run", run_id=run_id)
                return run_id
        finally:
            db.close()
    
    async def trigger_workflow(
        self,
        user_id: str,
        workflow_spec: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> str:
        """Trigger a compiled workflow in Tentackl"""
        # Get user's provider keys for all providers used in workflow
        db = SessionLocal()
        try:
            # Extract provider types from workflow spec
            provider_types = self._extract_provider_types(workflow_spec)
            
            # Get and decrypt provider credentials
            provider_credentials = {}
            for provider_type in provider_types:
                provider_key = db.query(ProviderKey).filter(
                    ProviderKey.user_id == user_id,
                    ProviderKey.provider_type == provider_type,
                    ProviderKey.is_active == True
                ).first()
                
                if provider_key:
                    provider_credentials[provider_type] = self._get_provider_credentials(provider_key)
            
            # Add provider credentials to parameters
            parameters["provider_credentials"] = provider_credentials
            
            # First, register the workflow spec in Tentackl
            # Then create a run from it
            # For now, we'll use the notification_delivery_v1 spec that's already registered
            # In production, you'd register the compiled spec first
            
            # Call Tentackl to create workflow run from spec
            # Note: This assumes the workflow spec is already registered in Tentackl
            # For dynamic workflows, you'd need to register the spec first via /api/workflow-specs
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use the notification_delivery_v1 spec name (assumes it's registered)
                response = await client.post(
                    f"{self.base_url}/api/workflow-runs/spec/name/notification_delivery_v1",
                    json={
                        "parameters": parameters,
                        "triggered_by": "mimic_notification_service"
                    },
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                return data.get("workflow_id", data.get("id", ""))
        finally:
            db.close()
    
    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow execution status from Tentackl"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/workflow-runs/{workflow_id}",
                    headers={
                        "X-API-Key": self.api_key
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Failed to get workflow status", error=str(e), workflow_id=workflow_id)
            return None
    
    def _get_provider_credentials(self, provider_key: ProviderKey) -> Dict[str, Any]:
        """Get decrypted provider credentials"""
        credentials = {}
        
        if provider_key.encrypted_api_key:
            credentials["api_key"] = encryption_service.decrypt(provider_key.encrypted_api_key)
        if provider_key.encrypted_secret:
            credentials["secret"] = encryption_service.decrypt(provider_key.encrypted_secret)
        if provider_key.webhook_url:
            credentials["webhook_url"] = provider_key.webhook_url
        if provider_key.bot_token:
            credentials["bot_token"] = encryption_service.decrypt(provider_key.bot_token)
        if provider_key.from_email:
            credentials["from_email"] = provider_key.from_email
        if provider_key.from_number:
            credentials["from_number"] = provider_key.from_number
        
        return credentials
    
    def _extract_provider_types(self, workflow_spec: Dict[str, Any]) -> list:
        """Extract provider types from workflow spec"""
        provider_types = []
        steps = workflow_spec.get("steps", [])
        
        for step in steps:
            task = step.get("task", {})
            provider = task.get("provider")
            if provider and provider not in provider_types:
                provider_types.append(provider)
        
        return provider_types

