"""Infrastructure adapter for integration OAuth provider registry."""

from __future__ import annotations

from typing import Optional

from src.domain.integrations import IntegrationOAuthProviderPort, IntegrationOAuthRegistryPort
from src.infrastructure.integrations.oauth_provider_registry import (
    get_oauth_provider,
    supports_oauth,
)


class OAuthRegistryAdapter(IntegrationOAuthRegistryPort):
    """Adapter exposing OAuth provider registry via the domain port."""

    def get_provider(self, provider_name: str) -> Optional[IntegrationOAuthProviderPort]:
        return get_oauth_provider(provider_name)

    def supports_oauth(self, provider_name: str) -> bool:
        return supports_oauth(provider_name)
