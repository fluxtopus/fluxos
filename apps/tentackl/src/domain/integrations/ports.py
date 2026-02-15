"""Domain ports for integrations and OAuth operations."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional, Protocol


class IntegrationOperationsPort(Protocol):
    """Port for integration lifecycle and action operations."""

    async def list_integrations(
        self,
        token: str,
        provider: Optional[str] = None,
        direction: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Any:
        ...

    async def get_integration(self, integration_id: str, token: str) -> Any:
        ...

    async def create_integration(self, data: Any, token: str) -> Any:
        ...

    async def update_integration(self, integration_id: str, data: Any, token: str) -> Any:
        ...

    async def delete_integration(self, integration_id: str, token: str) -> Any:
        ...

    async def add_credential(self, integration_id: str, credential: Any, token: str) -> Dict[str, Any]:
        ...

    async def set_inbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        ...

    async def get_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        ...

    async def delete_inbound_config(self, integration_id: str, token: str) -> None:
        ...

    async def set_outbound_config(self, integration_id: str, config: Any, token: str) -> Dict[str, Any]:
        ...

    async def get_outbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        ...

    async def delete_outbound_config(self, integration_id: str, token: str) -> None:
        ...

    async def execute_action(
        self,
        integration_id: str,
        action_type: str,
        params: Dict[str, Any],
        token: str,
    ) -> Any:
        ...

    async def get_inbound_webhook_url(self, integration_id: str, token: str) -> str:
        ...

    async def test_inbound_config(self, integration_id: str, token: str) -> Dict[str, Any]:
        ...


class IntegrationOAuthProviderPort(Protocol):
    """Port for OAuth provider operations."""

    def get_authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str:
        ...

    async def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> Any:
        ...

    async def refresh_token(self, refresh_token: str) -> Any:
        ...

    async def revoke_token(self, access_token: str) -> bool:
        ...


class IntegrationOAuthRegistryPort(Protocol):
    """Port for OAuth provider registry operations."""

    def get_provider(self, provider_name: str) -> Optional[IntegrationOAuthProviderPort]:
        ...

    def supports_oauth(self, provider_name: str) -> bool:
        ...


class IntegrationOAuthStatePort(Protocol):
    """Port for OAuth state persistence (PKCE + callback validation)."""

    async def store_state(self, state: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        ...

    async def get_state(self, state: str) -> Optional[Dict[str, Any]]:
        ...

    async def delete_state(self, state: str) -> None:
        ...

    async def pop_state(self, state: str) -> Optional[Dict[str, Any]]:
        ...


class IntegrationEventStreamPort(Protocol):
    """Port for integration SSE event streaming and publish."""

    def stream_events(self, integration_id: str) -> AsyncGenerator[str, None]:
        ...

    async def publish_event(self, integration_id: str, event: Dict[str, Any]) -> None:
        ...
