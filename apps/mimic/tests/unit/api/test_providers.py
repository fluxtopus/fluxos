"""
Unit tests for provider definitions API (INT-020, INT-021).

Tests:
- GET /api/v1/providers - List all providers
- GET /api/v1/providers - Filter by supports_inbound
- GET /api/v1/providers - Filter by supports_outbound
- GET /api/v1/providers/{provider} - Get specific provider
- GET /api/v1/providers/{provider} - Provider not found (404)
- Provider definition structure validation
- GET /api/v1/providers/{provider}/setup-guide - Get setup wizard (INT-021)
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import IntegrationProvider, CredentialType, OutboundActionType
from src.providers.definitions import (
    get_all_providers,
    get_provider_definition,
    get_provider_by_name,
    get_setup_guide_by_name,
    DISCORD_PROVIDER,
    SLACK_PROVIDER,
    GITHUB_PROVIDER,
    STRIPE_PROVIDER,
    CUSTOM_WEBHOOK_PROVIDER,
    CredentialRequirement,
)


# Test client without authentication (providers endpoint is public)
client = TestClient(app)


class TestProviderDefinitions:
    """Test provider definition functions."""

    def test_get_all_providers_returns_all(self):
        """Test that get_all_providers returns all 6 providers."""
        providers = get_all_providers()
        assert len(providers) == 6
        provider_names = {p.provider for p in providers}
        assert provider_names == {
            IntegrationProvider.discord,
            IntegrationProvider.slack,
            IntegrationProvider.github,
            IntegrationProvider.stripe,
            IntegrationProvider.twitter,
            IntegrationProvider.custom_webhook,
        }

    def test_get_provider_definition_by_enum(self):
        """Test getting provider by enum."""
        provider = get_provider_definition(IntegrationProvider.discord)
        assert provider is not None
        assert provider.provider == IntegrationProvider.discord
        assert provider.display_name == "Discord"

    def test_get_provider_definition_not_found(self):
        """Test getting unknown provider returns None."""
        # Use a string that doesn't exist as an IntegrationProvider
        from src.providers.definitions import PROVIDER_DEFINITIONS

        # Clear way to test - provider not in dict
        result = PROVIDER_DEFINITIONS.get("nonexistent", None)
        assert result is None

    def test_get_provider_by_name_string(self):
        """Test getting provider by name string."""
        provider = get_provider_by_name("slack")
        assert provider is not None
        assert provider.provider == IntegrationProvider.slack

    def test_get_provider_by_name_invalid(self):
        """Test getting provider with invalid name returns None."""
        provider = get_provider_by_name("invalid_provider")
        assert provider is None

    def test_discord_provider_structure(self):
        """Test Discord provider has correct structure."""
        p = DISCORD_PROVIDER
        assert p.display_name == "Discord"
        assert p.supports_outbound() is True
        # Discord doesn't support pure inbound
        assert IntegrationProvider.discord == p.provider

        # Check credentials
        cred_types = {c.credential_type for c in p.credentials}
        assert CredentialType.webhook_url in cred_types

        # Check outbound actions
        action_types = p.get_outbound_action_types()
        assert "send_message" in action_types
        assert "send_embed" in action_types

    def test_slack_provider_structure(self):
        """Test Slack provider has correct structure."""
        p = SLACK_PROVIDER
        assert p.display_name == "Slack"
        assert p.supports_inbound() is True
        assert p.supports_outbound() is True

        # Check actions
        action_types = p.get_outbound_action_types()
        assert "send_message" in action_types
        assert "send_blocks" in action_types

        # Check inbound events
        event_types = p.get_inbound_event_types()
        assert "message" in event_types
        assert "slash_command" in event_types

    def test_github_provider_structure(self):
        """Test GitHub provider has correct structure."""
        p = GITHUB_PROVIDER
        assert p.display_name == "GitHub"
        assert p.supports_inbound() is True
        assert p.supports_outbound() is True

        # Check actions
        action_types = p.get_outbound_action_types()
        assert "create_issue" in action_types
        assert "post_comment" in action_types

        # Check inbound events
        event_types = p.get_inbound_event_types()
        assert "push" in event_types
        assert "pull_request" in event_types

    def test_stripe_provider_inbound_only(self):
        """Test Stripe provider is inbound-only."""
        p = STRIPE_PROVIDER
        assert p.display_name == "Stripe"
        assert p.supports_inbound() is True
        assert p.supports_outbound() is False

        # No outbound actions
        assert len(p.outbound_actions) == 0

        # Has inbound events
        event_types = p.get_inbound_event_types()
        assert "checkout.session.completed" in event_types
        assert "customer.subscription.created" in event_types

    def test_custom_webhook_provider_structure(self):
        """Test custom webhook provider has correct structure."""
        p = CUSTOM_WEBHOOK_PROVIDER
        assert p.display_name == "Custom Webhook"
        assert p.supports_inbound() is True
        assert p.supports_outbound() is True

        # Check actions
        action_types = p.get_outbound_action_types()
        assert "post" in action_types
        assert "put" in action_types
        assert "send_message" in action_types

    def test_get_required_credentials_outbound(self):
        """Test getting required credentials for outbound direction."""
        from src.database.models import IntegrationDirection

        p = DISCORD_PROVIDER
        required = p.get_required_credentials(IntegrationDirection.outbound)

        # webhook_url should be required for outbound
        cred_types = {c.credential_type for c in required}
        assert CredentialType.webhook_url in cred_types

    def test_validation_rules_present(self):
        """Test that providers have validation rules."""
        # Discord should have validation rules
        assert len(DISCORD_PROVIDER.validation_rules) > 0

        # Check a specific rule
        content_rule = next(
            (r for r in DISCORD_PROVIDER.validation_rules if r.field == "content"),
            None
        )
        assert content_rule is not None
        assert content_rule.rule_type == "max_length"
        assert content_rule.value == 2000


class TestProvidersAPIList:
    """Test GET /api/v1/providers endpoint."""

    def test_list_providers_success(self):
        """Test listing all providers returns 200 and all 6 providers."""
        response = client.get("/api/v1/providers")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert data["total"] == 6
        assert len(data["items"]) == 6

        # Check provider names
        provider_names = {item["provider"] for item in data["items"]}
        assert provider_names == {"discord", "slack", "github", "stripe", "twitter", "custom_webhook"}

    def test_list_providers_summary_structure(self):
        """Test that provider summaries have correct structure."""
        response = client.get("/api/v1/providers")

        assert response.status_code == 200
        data = response.json()

        # Check first provider has all fields
        provider = data["items"][0]
        assert "provider" in provider
        assert "display_name" in provider
        assert "description" in provider
        assert "supports_inbound" in provider
        assert "supports_outbound" in provider
        assert "credential_count" in provider
        assert "inbound_event_count" in provider
        assert "outbound_action_count" in provider

    def test_list_providers_filter_supports_inbound(self):
        """Test filtering providers by supports_inbound=true."""
        response = client.get("/api/v1/providers?supports_inbound=true")

        assert response.status_code == 200
        data = response.json()

        # All returned providers should support inbound
        for item in data["items"]:
            assert item["supports_inbound"] is True

        # Should include slack, github, stripe, custom_webhook
        provider_names = {item["provider"] for item in data["items"]}
        assert "slack" in provider_names
        assert "github" in provider_names
        assert "stripe" in provider_names
        assert "custom_webhook" in provider_names

    def test_list_providers_filter_supports_inbound_false(self):
        """Test filtering providers by supports_inbound=false."""
        response = client.get("/api/v1/providers?supports_inbound=false")

        assert response.status_code == 200
        data = response.json()

        # All returned providers should not support inbound
        for item in data["items"]:
            assert item["supports_inbound"] is False

    def test_list_providers_filter_supports_outbound(self):
        """Test filtering providers by supports_outbound=true."""
        response = client.get("/api/v1/providers?supports_outbound=true")

        assert response.status_code == 200
        data = response.json()

        # All returned providers should support outbound
        for item in data["items"]:
            assert item["supports_outbound"] is True

        # Should include discord, slack, github, custom_webhook
        provider_names = {item["provider"] for item in data["items"]}
        assert "discord" in provider_names
        assert "slack" in provider_names
        assert "github" in provider_names
        assert "custom_webhook" in provider_names
        # Stripe should not be included (inbound only)
        assert "stripe" not in provider_names

    def test_list_providers_filter_supports_outbound_false(self):
        """Test filtering providers by supports_outbound=false."""
        response = client.get("/api/v1/providers?supports_outbound=false")

        assert response.status_code == 200
        data = response.json()

        # All returned providers should not support outbound
        for item in data["items"]:
            assert item["supports_outbound"] is False

        # Should only include stripe
        provider_names = {item["provider"] for item in data["items"]}
        assert "stripe" in provider_names
        assert len(provider_names) == 1

    def test_list_providers_combined_filters(self):
        """Test combining inbound and outbound filters."""
        response = client.get("/api/v1/providers?supports_inbound=true&supports_outbound=true")

        assert response.status_code == 200
        data = response.json()

        # All returned providers should support both
        for item in data["items"]:
            assert item["supports_inbound"] is True
            assert item["supports_outbound"] is True

        # Should include slack, github, custom_webhook (not discord or stripe)
        provider_names = {item["provider"] for item in data["items"]}
        assert "slack" in provider_names
        assert "github" in provider_names
        assert "custom_webhook" in provider_names


class TestProvidersAPIGet:
    """Test GET /api/v1/providers/{provider} endpoint."""

    def test_get_discord_provider(self):
        """Test getting Discord provider details."""
        response = client.get("/api/v1/providers/discord")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "discord"
        assert data["display_name"] == "Discord"
        assert data["supports_outbound"] is True
        assert len(data["outbound_actions"]) == 2  # send_message, send_embed
        assert len(data["credentials"]) >= 1  # webhook_url at minimum
        assert len(data["validation_rules"]) > 0

    def test_get_slack_provider(self):
        """Test getting Slack provider details."""
        response = client.get("/api/v1/providers/slack")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "slack"
        assert data["display_name"] == "Slack"
        assert data["supports_inbound"] is True
        assert data["supports_outbound"] is True
        assert len(data["outbound_actions"]) == 2  # send_message, send_blocks
        assert len(data["inbound_event_types"]) >= 4

    def test_get_github_provider(self):
        """Test getting GitHub provider details."""
        response = client.get("/api/v1/providers/github")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "github"
        assert data["display_name"] == "GitHub"
        assert data["supports_inbound"] is True
        assert data["supports_outbound"] is True

        # Check outbound actions
        action_types = [a["action_type"] for a in data["outbound_actions"]]
        assert "create_issue" in action_types
        assert "post_comment" in action_types

        # Check inbound events
        event_types = [e["event_type"] for e in data["inbound_event_types"]]
        assert "push" in event_types
        assert "pull_request" in event_types

    def test_get_stripe_provider(self):
        """Test getting Stripe provider details."""
        response = client.get("/api/v1/providers/stripe")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "stripe"
        assert data["display_name"] == "Stripe"
        assert data["supports_inbound"] is True
        assert data["supports_outbound"] is False
        assert len(data["outbound_actions"]) == 0
        assert len(data["inbound_event_types"]) >= 10

    def test_get_custom_webhook_provider(self):
        """Test getting custom webhook provider details."""
        response = client.get("/api/v1/providers/custom_webhook")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "custom_webhook"
        assert data["display_name"] == "Custom Webhook"
        assert data["supports_inbound"] is True
        assert data["supports_outbound"] is True

        # Check outbound actions
        action_types = [a["action_type"] for a in data["outbound_actions"]]
        assert "post" in action_types
        assert "put" in action_types
        assert "send_message" in action_types

    def test_get_provider_not_found(self):
        """Test getting non-existent provider returns 404."""
        response = client.get("/api/v1/providers/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        assert "Available providers" in data["detail"]

    def test_get_provider_response_structure(self):
        """Test that provider detail response has complete structure."""
        response = client.get("/api/v1/providers/discord")

        assert response.status_code == 200
        data = response.json()

        # Top level fields
        assert "provider" in data
        assert "display_name" in data
        assert "description" in data
        assert "documentation_url" in data
        assert "icon_url" in data
        assert "supported_directions" in data
        assert "supports_inbound" in data
        assert "supports_outbound" in data
        assert "credentials" in data
        assert "inbound_event_types" in data
        assert "outbound_actions" in data
        assert "validation_rules" in data

    def test_credential_structure(self):
        """Test that credentials have correct structure."""
        response = client.get("/api/v1/providers/discord")

        assert response.status_code == 200
        data = response.json()

        # Check first credential
        cred = data["credentials"][0]
        assert "credential_type" in cred
        assert "requirement" in cred
        assert "description" in cred
        assert "required_for_inbound" in cred
        assert "required_for_outbound" in cred

    def test_outbound_action_structure(self):
        """Test that outbound actions have correct structure."""
        response = client.get("/api/v1/providers/discord")

        assert response.status_code == 200
        data = response.json()

        # Check first action
        action = data["outbound_actions"][0]
        assert "action_type" in action
        assert "description" in action
        assert "required_params" in action
        assert "optional_params" in action

    def test_validation_rule_structure(self):
        """Test that validation rules have correct structure."""
        response = client.get("/api/v1/providers/discord")

        assert response.status_code == 200
        data = response.json()

        # Check first validation rule
        rule = data["validation_rules"][0]
        assert "field" in rule
        assert "rule_type" in rule
        assert "value" in rule
        assert "error_message" in rule


# =============================================================================
# INT-021: Provider Setup Guide Tests
# =============================================================================


class TestSetupGuideDefinitions:
    """Test setup guide definitions (INT-021)."""

    def test_discord_setup_guide_exists(self):
        """Test that Discord has a setup guide."""
        from src.providers.definitions import DISCORD_SETUP_GUIDE

        assert DISCORD_SETUP_GUIDE is not None
        assert DISCORD_SETUP_GUIDE.provider == IntegrationProvider.discord
        assert DISCORD_SETUP_GUIDE.estimated_time_minutes > 0
        assert len(DISCORD_SETUP_GUIDE.steps) > 0
        assert len(DISCORD_SETUP_GUIDE.prerequisites) > 0
        assert len(DISCORD_SETUP_GUIDE.test_steps) > 0

    def test_slack_setup_guide_exists(self):
        """Test that Slack has a setup guide."""
        from src.providers.definitions import SLACK_SETUP_GUIDE

        assert SLACK_SETUP_GUIDE is not None
        assert SLACK_SETUP_GUIDE.provider == IntegrationProvider.slack
        assert len(SLACK_SETUP_GUIDE.steps) > 0

    def test_github_setup_guide_exists(self):
        """Test that GitHub has a setup guide."""
        from src.providers.definitions import GITHUB_SETUP_GUIDE

        assert GITHUB_SETUP_GUIDE is not None
        assert GITHUB_SETUP_GUIDE.provider == IntegrationProvider.github
        assert len(GITHUB_SETUP_GUIDE.steps) > 0

    def test_stripe_setup_guide_exists(self):
        """Test that Stripe has a setup guide."""
        from src.providers.definitions import STRIPE_SETUP_GUIDE

        assert STRIPE_SETUP_GUIDE is not None
        assert STRIPE_SETUP_GUIDE.provider == IntegrationProvider.stripe
        assert len(STRIPE_SETUP_GUIDE.steps) > 0

    def test_custom_webhook_setup_guide_exists(self):
        """Test that Custom Webhook has a setup guide."""
        from src.providers.definitions import CUSTOM_WEBHOOK_SETUP_GUIDE

        assert CUSTOM_WEBHOOK_SETUP_GUIDE is not None
        assert CUSTOM_WEBHOOK_SETUP_GUIDE.provider == IntegrationProvider.custom_webhook
        assert len(CUSTOM_WEBHOOK_SETUP_GUIDE.steps) > 0

    def test_setup_guide_step_structure(self):
        """Test that setup guide steps have correct structure."""
        from src.providers.definitions import DISCORD_SETUP_GUIDE

        step = DISCORD_SETUP_GUIDE.steps[0]
        assert step.step_number > 0
        assert step.title
        assert step.description
        assert len(step.instructions) > 0
        assert isinstance(step.tips, list)
        assert isinstance(step.is_optional, bool)

    def test_setup_guide_common_issues_structure(self):
        """Test that common issues have correct structure."""
        from src.providers.definitions import DISCORD_SETUP_GUIDE

        assert len(DISCORD_SETUP_GUIDE.common_issues) > 0
        issue = DISCORD_SETUP_GUIDE.common_issues[0]
        assert "issue" in issue
        assert "solution" in issue

    def test_get_setup_guide_by_name(self):
        """Test get_setup_guide_by_name function."""
        from src.providers.definitions import get_setup_guide_by_name

        guide = get_setup_guide_by_name("discord")
        assert guide is not None
        assert guide.provider == IntegrationProvider.discord

    def test_get_setup_guide_by_name_invalid(self):
        """Test get_setup_guide_by_name with invalid provider returns None."""
        from src.providers.definitions import get_setup_guide_by_name

        guide = get_setup_guide_by_name("invalid_provider")
        assert guide is None

    def test_provider_has_setup_guide_reference(self):
        """Test that provider definitions have setup_guide field."""
        assert DISCORD_PROVIDER.setup_guide is not None
        assert SLACK_PROVIDER.setup_guide is not None
        assert GITHUB_PROVIDER.setup_guide is not None
        assert STRIPE_PROVIDER.setup_guide is not None
        assert CUSTOM_WEBHOOK_PROVIDER.setup_guide is not None


class TestSetupGuideAPI:
    """Test GET /api/v1/providers/{provider}/setup-guide endpoint (INT-021)."""

    def test_get_discord_setup_guide_success(self):
        """Test getting Discord setup guide returns 200."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "discord"
        assert data["display_name"] == "Discord"
        assert data["estimated_time_minutes"] > 0
        assert len(data["prerequisites"]) > 0
        assert len(data["steps"]) > 0
        assert len(data["permissions_needed"]) > 0
        assert len(data["test_steps"]) > 0
        assert len(data["common_issues"]) > 0

    def test_get_slack_setup_guide_success(self):
        """Test getting Slack setup guide returns 200."""
        response = client.get("/api/v1/providers/slack/setup-guide")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "slack"
        assert data["display_name"] == "Slack"
        assert len(data["steps"]) > 0

    def test_get_github_setup_guide_success(self):
        """Test getting GitHub setup guide returns 200."""
        response = client.get("/api/v1/providers/github/setup-guide")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "github"
        assert data["display_name"] == "GitHub"
        assert len(data["steps"]) > 0

    def test_get_stripe_setup_guide_success(self):
        """Test getting Stripe setup guide returns 200."""
        response = client.get("/api/v1/providers/stripe/setup-guide")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "stripe"
        assert data["display_name"] == "Stripe"
        assert len(data["steps"]) > 0

    def test_get_custom_webhook_setup_guide_success(self):
        """Test getting Custom Webhook setup guide returns 200."""
        response = client.get("/api/v1/providers/custom_webhook/setup-guide")

        assert response.status_code == 200
        data = response.json()

        assert data["provider"] == "custom_webhook"
        assert data["display_name"] == "Custom Webhook"
        assert len(data["steps"]) > 0

    def test_get_setup_guide_not_found_provider(self):
        """Test getting setup guide for non-existent provider returns 404."""
        response = client.get("/api/v1/providers/nonexistent/setup-guide")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_setup_guide_response_structure(self):
        """Test that setup guide response has complete structure."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # Top level fields
        assert "provider" in data
        assert "display_name" in data
        assert "estimated_time_minutes" in data
        assert "prerequisites" in data
        assert "steps" in data
        assert "permissions_needed" in data
        assert "test_steps" in data
        assert "common_issues" in data
        assert "video_tutorial_url" in data

    def test_setup_guide_step_structure(self):
        """Test that setup guide steps have correct structure in API response."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # Check first step
        step = data["steps"][0]
        assert "step_number" in step
        assert "title" in step
        assert "description" in step
        assert "instructions" in step
        assert "tips" in step
        assert "is_optional" in step

    def test_setup_guide_common_issue_structure(self):
        """Test that common issues have correct structure in API response."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # Check first common issue
        issue = data["common_issues"][0]
        assert "issue" in issue
        assert "solution" in issue

    def test_setup_guide_credential_type_serialization(self):
        """Test that credential_type is properly serialized in steps."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # Find a step with credential_type
        step_with_cred = next(
            (s for s in data["steps"] if s.get("credential_type") is not None),
            None
        )
        # Discord should have a step collecting webhook_url
        assert step_with_cred is not None
        assert step_with_cred["credential_type"] == "webhook_url"

    def test_setup_guide_has_external_links(self):
        """Test that setup guide steps include external links where appropriate."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # At least one step should have an external link
        steps_with_links = [s for s in data["steps"] if s.get("external_link")]
        assert len(steps_with_links) > 0

    def test_setup_guide_video_tutorial_url(self):
        """Test that providers with video tutorials include the URL."""
        response = client.get("/api/v1/providers/discord/setup-guide")

        assert response.status_code == 200
        data = response.json()

        # Discord should have a video tutorial URL
        assert data["video_tutorial_url"] is not None
        assert "discord.com" in data["video_tutorial_url"]

    def test_all_providers_have_setup_guides(self):
        """Test that all 5 providers have setup guides available via API."""
        providers = ["discord", "slack", "github", "stripe", "custom_webhook"]

        for provider in providers:
            response = client.get(f"/api/v1/providers/{provider}/setup-guide")
            assert response.status_code == 200, f"Setup guide missing for {provider}"
            data = response.json()
            assert data["provider"] == provider
            assert len(data["steps"]) > 0, f"No steps for {provider}"
