"""Application use cases for integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Optional

from src.domain.integrations import IntegrationEventStreamPort, IntegrationOperationsPort


@dataclass
class IntegrationUseCases:
    """Application-layer orchestration for integrations."""

    integration_ops: IntegrationOperationsPort

    async def list_integrations(
        self,
        token: str,
        provider: Optional[str] = None,
        direction: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Any:
        return await self.integration_ops.list_integrations(
            token=token,
            provider=provider,
            direction=direction,
            status=status,
        )

    async def get_integration(self, integration_id: str, token: str) -> Any:
        return await self.integration_ops.get_integration(
            integration_id=integration_id,
            token=token,
        )

    async def create_integration(self, data: Any, token: str) -> Any:
        return await self.integration_ops.create_integration(data=data, token=token)

    async def update_integration(self, integration_id: str, data: Any, token: str) -> Any:
        return await self.integration_ops.update_integration(
            integration_id=integration_id,
            data=data,
            token=token,
        )

    async def delete_integration(self, integration_id: str, token: str) -> Any:
        return await self.integration_ops.delete_integration(
            integration_id=integration_id,
            token=token,
        )

    async def add_credential(self, integration_id: str, credential: Any, token: str) -> Dict[str, Any]:
        return await self.integration_ops.add_credential(
            integration_id=integration_id,
            credential=credential,
            token=token,
        )

    async def set_inbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        return await self.integration_ops.set_inbound_config(
            integration_id=integration_id,
            config=config,
            token=token,
        )

    async def get_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        return await self.integration_ops.get_inbound_config(
            integration_id=integration_id,
            token=token,
        )

    async def delete_inbound_config(self, integration_id: str, token: str) -> None:
        await self.integration_ops.delete_inbound_config(
            integration_id=integration_id,
            token=token,
        )

    async def set_outbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        return await self.integration_ops.set_outbound_config(
            integration_id=integration_id,
            config=config,
            token=token,
        )

    async def get_outbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        return await self.integration_ops.get_outbound_config(
            integration_id=integration_id,
            token=token,
        )

    async def delete_outbound_config(self, integration_id: str, token: str) -> None:
        await self.integration_ops.delete_outbound_config(
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
        return await self.integration_ops.execute_action(
            integration_id=integration_id,
            action_type=action_type,
            params=params,
            token=token,
        )

    async def get_inbound_webhook_url(self, integration_id: str, token: str) -> str:
        return await self.integration_ops.get_inbound_webhook_url(
            integration_id=integration_id,
            token=token,
        )

    async def test_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        return await self.integration_ops.test_inbound_config(
            integration_id=integration_id,
            token=token,
        )


@dataclass
class IntegrationEventStreamUseCases:
    """Application-layer orchestration for integrations SSE stream operations."""

    event_stream_ops: IntegrationEventStreamPort

    def stream_events(self, integration_id: str) -> AsyncGenerator[str, None]:
        return self.event_stream_ops.stream_events(integration_id=integration_id)

    async def publish_event(self, integration_id: str, event: Dict[str, Any]) -> None:
        await self.event_stream_ops.publish_event(
            integration_id=integration_id,
            event=event,
        )
