"""Infrastructure registry for OAuth-capable integration providers."""

from __future__ import annotations

from typing import Optional

from src.infrastructure.integrations.oauth_provider_base import IntegrationOAuthProvider
from src.infrastructure.integrations.twitter_oauth_provider import TwitterOAuthProvider

INTEGRATION_OAUTH_PROVIDERS: dict[str, type[IntegrationOAuthProvider]] = {
    "twitter": TwitterOAuthProvider,
}


def get_oauth_provider(provider_name: str) -> Optional[IntegrationOAuthProvider]:
    """Get an instantiated OAuth provider by name."""

    provider_cls = INTEGRATION_OAUTH_PROVIDERS.get(provider_name)
    if provider_cls is None:
        return None
    return provider_cls()


def supports_oauth(provider_name: str) -> bool:
    """Check if a provider supports OAuth."""

    return provider_name in INTEGRATION_OAUTH_PROVIDERS
