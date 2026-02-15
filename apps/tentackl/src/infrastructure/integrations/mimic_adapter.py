"""Infrastructure adapter for Mimic integration operations."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.clients import mimic as mimic_client
from src.domain.integrations import IntegrationOperationsPort


class MimicIntegrationAdapter(IntegrationOperationsPort):
    """Adapter that exposes Mimic integration operations through the domain port."""

    async def list_integrations(
        self,
        token: str,
        provider: Optional[str] = None,
        direction: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Any:
        return await mimic_client.list_integrations(
            token=token,
            provider=provider,
            direction=direction,
            status=status,
        )

    async def get_integration(self, integration_id: str, token: str) -> Any:
        return await mimic_client.get_integration(
            integration_id=integration_id,
            token=token,
        )

    async def create_integration(self, data: Any, token: str) -> Any:
        return await mimic_client.create_integration(data=data, token=token)

    async def update_integration(self, integration_id: str, data: Any, token: str) -> Any:
        return await mimic_client.update_integration(
            integration_id=integration_id,
            data=data,
            token=token,
        )

    async def delete_integration(self, integration_id: str, token: str) -> Any:
        return await mimic_client.delete_integration(
            integration_id=integration_id,
            token=token,
        )

    async def add_credential(self, integration_id: str, credential: Any, token: str) -> Dict[str, Any]:
        return await mimic_client.add_credential(
            integration_id=integration_id,
            credential=credential,
            token=token,
        )

    async def set_inbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        return await mimic_client.set_inbound_config(
            integration_id=integration_id,
            config=config,
            token=token,
        )

    async def get_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        async with mimic_client.get_client() as client:
            result = await client.get_inbound_config(
                integration_id=integration_id,
                token=token,
            )
            return result.model_dump()

    async def delete_inbound_config(self, integration_id: str, token: str) -> None:
        async with mimic_client.get_client() as client:
            await client.delete_inbound_config(
                integration_id=integration_id,
                token=token,
            )

    async def set_outbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        return await mimic_client.set_outbound_config(
            integration_id=integration_id,
            config=config,
            token=token,
        )

    async def get_outbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        async with mimic_client.get_client() as client:
            result = await client.get_outbound_config(
                integration_id=integration_id,
                token=token,
            )
            return result.model_dump()

    async def delete_outbound_config(self, integration_id: str, token: str) -> None:
        async with mimic_client.get_client() as client:
            await client.delete_outbound_config(
                integration_id=integration_id,
                token=token,
            )

    async def execute_action(
        self,
        integration_id: str,
        action_type: str,
        params: Dict[str, Any],
        token: str,
    ) -> Any:
        return await mimic_client.execute_action(
            integration_id=integration_id,
            action_type=action_type,
            params=params,
            token=token,
        )

    async def get_inbound_webhook_url(self, integration_id: str, token: str) -> str:
        return await mimic_client.get_inbound_webhook_url(
            integration_id=integration_id,
            token=token,
        )

    async def test_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        async with mimic_client.get_client() as client:
            http_client = client._get_client()
            headers = client._get_headers(token=token)
            response = await http_client.post(
                f"/api/v1/integrations/{integration_id}/inbound/test",
                headers=headers,
            )
            if response.status_code >= 400:
                client._handle_error(response)
            return response.json()
