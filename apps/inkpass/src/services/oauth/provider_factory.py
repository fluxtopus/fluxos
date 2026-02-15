"""OAuth Provider Factory - Registry pattern for managing providers"""

from typing import Dict, Type, Optional
from .provider_interface import OAuthProviderInterface


class OAuthProviderFactory:
    """
    Factory for creating and managing OAuth providers.

    Uses the Registry pattern to allow dynamic registration of OAuth providers.
    New providers can be added without modifying existing code.

    Single Responsibility: Manage provider registration and instantiation.

    Usage:
        # Register a provider
        OAuthProviderFactory.register("google", GoogleOAuthProvider)

        # Create a provider instance
        provider = OAuthProviderFactory.create("google", client_id="...", ...)
    """

    # Registry of provider classes
    _providers: Dict[str, Type[OAuthProviderInterface]] = {}

    @classmethod
    def register(cls, provider_name: str, provider_class: Type[OAuthProviderInterface]):
        """
        Register an OAuth provider class.

        Args:
            provider_name: Unique name for the provider (e.g., "google", "apple")
            provider_class: Provider class that implements OAuthProviderInterface

        Raises:
            ValueError: If provider is already registered or doesn't implement interface
        """
        if not issubclass(provider_class, OAuthProviderInterface):
            raise ValueError(
                f"Provider class {provider_class.__name__} must implement OAuthProviderInterface"
            )

        if provider_name in cls._providers:
            raise ValueError(f"Provider '{provider_name}' is already registered")

        cls._providers[provider_name] = provider_class

    @classmethod
    def unregister(cls, provider_name: str):
        """
        Unregister an OAuth provider.

        Args:
            provider_name: Name of provider to unregister
        """
        if provider_name in cls._providers:
            del cls._providers[provider_name]

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> OAuthProviderInterface:
        """
        Create an instance of a registered OAuth provider.

        Args:
            provider_name: Name of the provider to create
            **kwargs: Arguments to pass to provider constructor

        Returns:
            Instance of the OAuth provider

        Raises:
            ValueError: If provider is not registered
        """
        if provider_name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Provider '{provider_name}' not found. "
                f"Available providers: {available or 'none'}"
            )

        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)

    @classmethod
    def is_registered(cls, provider_name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            provider_name: Name of the provider

        Returns:
            True if provider is registered, False otherwise
        """
        return provider_name in cls._providers

    @classmethod
    def list_providers(cls) -> list[str]:
        """
        List all registered provider names.

        Returns:
            List of registered provider names
        """
        return list(cls._providers.keys())

    @classmethod
    def clear_registry(cls):
        """
        Clear all registered providers.

        Useful for testing or resetting the factory.
        """
        cls._providers.clear()


def register_default_providers():
    """
    Register the default OAuth providers.

    This function should be called during application startup to register
    all built-in OAuth providers.
    """
    from .google_provider import GoogleOAuthProvider
    from .mock_provider import MockOAuthProvider

    if not OAuthProviderFactory.is_registered("google"):
        OAuthProviderFactory.register("google", GoogleOAuthProvider)
    if not OAuthProviderFactory.is_registered("mock"):
        OAuthProviderFactory.register("mock", MockOAuthProvider)
    # Future providers can be registered here:
    # OAuthProviderFactory.register("apple", AppleOAuthProvider)
    # OAuthProviderFactory.register("github", GitHubOAuthProvider)
