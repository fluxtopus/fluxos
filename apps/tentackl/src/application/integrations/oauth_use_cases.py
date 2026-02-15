"""Application use cases for integration OAuth flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import hashlib
import secrets
from base64 import urlsafe_b64encode

from mimic.models import CredentialCreate, CredentialType

from src.domain.integrations import (
    IntegrationOperationsPort,
    IntegrationOAuthRegistryPort,
    IntegrationOAuthProviderPort,
    IntegrationOAuthStatePort,
)


class IntegrationOAuthStateError(ValueError):
    """Raised when OAuth state is missing or invalid."""


class IntegrationOAuthExchangeError(Exception):
    """Raised when OAuth code exchange fails."""

    def __init__(self, integration_id: str, message: str) -> None:
        super().__init__(message)
        self.integration_id = integration_id


@dataclass
class IntegrationOAuthUseCases:
    """Application-layer orchestration for OAuth flows."""

    integration_ops: IntegrationOperationsPort
    oauth_registry: IntegrationOAuthRegistryPort
    oauth_state: IntegrationOAuthStatePort

    async def get_integration_provider_name(self, integration_id: str, token: str) -> str:
        integration = await self.integration_ops.get_integration(
            integration_id=integration_id,
            token=token,
        )
        return integration.provider if isinstance(integration.provider, str) else integration.provider.value

    def supports_oauth(self, provider_name: str) -> bool:
        return self.oauth_registry.supports_oauth(provider_name)

    def get_provider(self, provider_name: str) -> Optional[IntegrationOAuthProviderPort]:
        return self.oauth_registry.get_provider(provider_name)

    def build_authorization_url(
        self,
        provider_name: str,
        state: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Unknown OAuth provider: {provider_name}")
        return provider.get_authorization_url(
            state=state,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
        )

    def _generate_pkce(self) -> Tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge (S256)."""
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    async def start_authorization(
        self,
        integration_id: str,
        user_id: str,
        token: str,
        redirect_uri: str,
        state_ttl_seconds: int,
    ) -> str:
        provider_name = await self.get_integration_provider_name(
            integration_id=integration_id,
            token=token,
        )

        if not self.supports_oauth(provider_name):
            raise ValueError(f"Provider '{provider_name}' does not support OAuth")

        code_verifier, code_challenge = self._generate_pkce()
        state_token = secrets.token_urlsafe(32)

        await self.oauth_state.store_state(
            state_token,
            {
                "integration_id": integration_id,
                "provider": provider_name,
                "code_verifier": code_verifier,
                "user_id": user_id,
                "bearer_token": token,
            },
            state_ttl_seconds,
        )

        return self.build_authorization_url(
            provider_name=provider_name,
            state=state_token,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
        )

    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> str:
        state_data = await self.oauth_state.pop_state(state)
        if not state_data:
            raise IntegrationOAuthStateError("Invalid or expired OAuth state")

        integration_id = state_data["integration_id"]
        provider_name = state_data["provider"]
        code_verifier = state_data["code_verifier"]
        bearer_token = state_data["bearer_token"]

        try:
            await self.exchange_code_and_store_credentials(
                integration_id=integration_id,
                provider_name=provider_name,
                code=code,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                token=bearer_token,
            )
        except Exception as exc:
            raise IntegrationOAuthExchangeError(integration_id, str(exc)) from exc

        return integration_id

    async def exchange_code_and_store_credentials(
        self,
        integration_id: str,
        provider_name: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        token: str,
    ) -> None:
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Unknown OAuth provider: {provider_name}")

        token_result = await provider.exchange_code(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )

        await self.integration_ops.add_credential(
            integration_id=integration_id,
            credential=CredentialCreate(
                credential_type=CredentialType.oauth_token,
                value=token_result.access_token,
                credential_metadata={
                    "token_type": token_result.token_type,
                    "scope": token_result.scope,
                    "provider": provider_name,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                },
                expires_at=(
                    (datetime.now(timezone.utc) + timedelta(seconds=token_result.expires_in)).isoformat()
                    if token_result.expires_in
                    else None
                ),
            ),
            token=token,
        )

        if token_result.refresh_token:
            await self.integration_ops.add_credential(
                integration_id=integration_id,
                credential=CredentialCreate(
                    credential_type=CredentialType.oauth_token,
                    value=token_result.refresh_token,
                    credential_metadata={
                        "token_subtype": "refresh_token",
                        "provider": provider_name,
                    },
                ),
                token=token,
            )
