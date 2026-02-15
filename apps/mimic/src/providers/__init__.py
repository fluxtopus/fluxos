"""
Provider definitions module (INT-020, INT-021).

Provides provider definitions and setup guides for all supported integration providers.
"""

from src.providers.definitions import (
    CredentialDefinition,
    CredentialRequirement,
    InboundEventType,
    OutboundActionDefinition,
    ProviderDefinition,
    ProviderSetupGuide,
    SetupStep,
    ValidationRule,
    PROVIDER_DEFINITIONS,
    get_provider_definition,
    get_all_providers,
    get_provider_by_name,
    get_setup_guide_by_name,
    DISCORD_PROVIDER,
    SLACK_PROVIDER,
    GITHUB_PROVIDER,
    STRIPE_PROVIDER,
    CUSTOM_WEBHOOK_PROVIDER,
    DISCORD_SETUP_GUIDE,
    SLACK_SETUP_GUIDE,
    GITHUB_SETUP_GUIDE,
    STRIPE_SETUP_GUIDE,
    CUSTOM_WEBHOOK_SETUP_GUIDE,
)

__all__ = [
    "CredentialDefinition",
    "CredentialRequirement",
    "InboundEventType",
    "OutboundActionDefinition",
    "ProviderDefinition",
    "ProviderSetupGuide",
    "SetupStep",
    "ValidationRule",
    "PROVIDER_DEFINITIONS",
    "get_provider_definition",
    "get_all_providers",
    "get_provider_by_name",
    "get_setup_guide_by_name",
    "DISCORD_PROVIDER",
    "SLACK_PROVIDER",
    "GITHUB_PROVIDER",
    "STRIPE_PROVIDER",
    "CUSTOM_WEBHOOK_PROVIDER",
    "DISCORD_SETUP_GUIDE",
    "SLACK_SETUP_GUIDE",
    "GITHUB_SETUP_GUIDE",
    "STRIPE_SETUP_GUIDE",
    "CUSTOM_WEBHOOK_SETUP_GUIDE",
]
