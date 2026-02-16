"""
Provider definition system (INT-020).

Provides provider definitions for all supported integration providers.
Each provider defines:
- Required credential types
- Supported inbound event types
- Supported outbound action types
- Validation rules

Provider definitions are stored in code (config-based) for:
- Version control and auditability
- Easy deployment without database migrations
- Clear documentation and type safety
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.database.models import (
    CredentialType,
    IntegrationDirection,
    IntegrationProvider,
    OutboundActionType,
)


class CredentialRequirement(str, Enum):
    """Whether a credential is required, optional, or conditional."""
    required = "required"
    optional = "optional"
    conditional = "conditional"  # Required for certain features


@dataclass
class CredentialDefinition:
    """Definition of a credential type for a provider."""
    credential_type: CredentialType
    requirement: CredentialRequirement
    description: str
    example_format: Optional[str] = None
    validation_pattern: Optional[str] = None  # Regex pattern for validation
    max_length: Optional[int] = None
    required_for_inbound: bool = False
    required_for_outbound: bool = False


@dataclass
class InboundEventType:
    """Definition of an inbound event type."""
    event_type: str
    description: str
    example_payload: Optional[dict] = None


@dataclass
class OutboundActionDefinition:
    """Definition of an outbound action type."""
    action_type: OutboundActionType
    description: str
    required_params: list[str] = field(default_factory=list)
    optional_params: list[str] = field(default_factory=list)
    rate_limit_recommendation: Optional[dict] = None  # {"requests": int, "window_seconds": int}


@dataclass
class ValidationRule:
    """Validation rule for provider-specific constraints."""
    field: str
    rule_type: str  # "max_length", "min_length", "pattern", "range", "enum"
    value: any
    error_message: str


@dataclass
class SetupStep:
    """A single step in the provider setup wizard."""
    step_number: int
    title: str
    description: str
    instructions: list[str]  # Ordered list of instructions
    screenshot_url: Optional[str] = None  # URL to screenshot/image
    external_link: Optional[str] = None  # Link to external page (e.g., Discord settings)
    credential_type: Optional[CredentialType] = None  # Credential collected in this step
    tips: list[str] = field(default_factory=list)  # Optional tips/warnings
    is_optional: bool = False


@dataclass
class ProviderSetupGuide:
    """
    Complete setup guide for an integration provider.

    Contains step-by-step instructions for setting up the integration,
    including credentials, permissions, and verification steps.
    """
    provider: IntegrationProvider
    estimated_time_minutes: int
    prerequisites: list[str]  # What user needs before starting
    steps: list[SetupStep]
    permissions_needed: list[str]  # Permissions/scopes required
    test_steps: list[str]  # Steps to verify setup is working
    common_issues: list[dict]  # {"issue": str, "solution": str}
    video_tutorial_url: Optional[str] = None


@dataclass
class ProviderDefinition:
    """
    Complete definition of an integration provider.

    Contains all information needed to:
    - Validate integration configurations
    - Display setup guidance in UI
    - Document supported features
    """
    provider: IntegrationProvider
    display_name: str
    description: str
    documentation_url: Optional[str]
    icon_url: Optional[str]
    supported_directions: list[IntegrationDirection]
    credentials: list[CredentialDefinition]
    inbound_event_types: list[InboundEventType]
    outbound_actions: list[OutboundActionDefinition]
    validation_rules: list[ValidationRule] = field(default_factory=list)
    setup_guide: Optional[ProviderSetupGuide] = None

    def get_required_credentials(self, direction: IntegrationDirection) -> list[CredentialDefinition]:
        """Get credentials required for a given direction."""
        required = []
        for cred in self.credentials:
            if cred.requirement == CredentialRequirement.required:
                required.append(cred)
            elif direction in [IntegrationDirection.inbound, IntegrationDirection.bidirectional] and cred.required_for_inbound:
                required.append(cred)
            elif direction in [IntegrationDirection.outbound, IntegrationDirection.bidirectional] and cred.required_for_outbound:
                required.append(cred)
        return required

    def supports_inbound(self) -> bool:
        """Check if provider supports inbound webhooks."""
        return IntegrationDirection.inbound in self.supported_directions or \
               IntegrationDirection.bidirectional in self.supported_directions

    def supports_outbound(self) -> bool:
        """Check if provider supports outbound actions."""
        return IntegrationDirection.outbound in self.supported_directions or \
               IntegrationDirection.bidirectional in self.supported_directions

    def get_outbound_action_types(self) -> list[str]:
        """Get list of supported outbound action type values."""
        return [action.action_type.value for action in self.outbound_actions]

    def get_inbound_event_types(self) -> list[str]:
        """Get list of supported inbound event type values."""
        return [event.event_type for event in self.inbound_event_types]


# =============================================================================
# Setup Guides (INT-021)
# =============================================================================

DISCORD_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.discord,
    estimated_time_minutes=3,
    prerequisites=[
        "A Discord server where you have administrator or manage webhooks permission",
        "Access to Discord via web browser or desktop app",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Open Server Settings",
            description="Navigate to your Discord server's settings to access integrations.",
            instructions=[
                "Open Discord and go to the server where you want to send messages",
                "Click on the server name at the top of the channel list",
                "Select 'Server Settings' from the dropdown menu",
            ],
            external_link="https://discord.com/channels/@me",
            tips=["You need 'Manage Webhooks' permission to create webhooks"],
        ),
        SetupStep(
            step_number=2,
            title="Access Integrations",
            description="Find the integrations section where webhooks are managed.",
            instructions=[
                "In the left sidebar, scroll down to 'Apps'",
                "Click on 'Integrations'",
                "You'll see the Webhooks section",
            ],
        ),
        SetupStep(
            step_number=3,
            title="Create a Webhook",
            description="Create a new webhook for your integration.",
            instructions=[
                "Click on 'Webhooks'",
                "Click 'New Webhook' button",
                "Give your webhook a name (e.g., 'fluxos Notifications')",
                "Select the channel where messages should be posted",
                "Optionally upload a custom avatar for the webhook",
            ],
            tips=[
                "The webhook name will appear as the sender name in messages",
                "You can change the channel later if needed",
            ],
        ),
        SetupStep(
            step_number=4,
            title="Copy Webhook URL",
            description="Copy the webhook URL to use in your integration.",
            instructions=[
                "Click 'Copy Webhook URL' button",
                "The URL will be copied to your clipboard",
                "The URL format is: https://discord.com/api/webhooks/[ID]/[TOKEN]",
            ],
            credential_type=CredentialType.webhook_url,
            tips=[
                "Keep this URL private - anyone with it can post to your channel",
                "You can regenerate the URL if it's compromised",
            ],
        ),
        SetupStep(
            step_number=5,
            title="Add to fluxos",
            description="Configure the integration in fluxos with your webhook URL.",
            instructions=[
                "Return to fluxos and create a new Discord integration",
                "Paste the webhook URL in the credentials section",
                "Configure outbound settings (message type, rate limits)",
                "Save the integration",
            ],
        ),
    ],
    permissions_needed=[
        "Manage Webhooks - Required to create and manage webhooks",
    ],
    test_steps=[
        "Use the 'Test' button in fluxos to send a test message",
        "Check that the message appears in the selected Discord channel",
        "Verify the message displays with the correct webhook name and avatar",
    ],
    common_issues=[
        {
            "issue": "Webhook URL is invalid",
            "solution": "Ensure the URL starts with 'https://discord.com/api/webhooks/' and contains both webhook ID and token",
        },
        {
            "issue": "Messages not appearing in channel",
            "solution": "Verify the webhook hasn't been deleted, check if the channel still exists, and confirm no Discord permissions block the bot",
        },
        {
            "issue": "Rate limit errors",
            "solution": "Discord allows about 30 messages per minute per webhook. Reduce message frequency or use multiple webhooks",
        },
    ],
    video_tutorial_url="https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks",
)


SLACK_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.slack,
    estimated_time_minutes=5,
    prerequisites=[
        "A Slack workspace where you have permission to add apps",
        "Admin access or ability to request app installation",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Create a Slack App",
            description="Create a new Slack app to get webhook capabilities.",
            instructions=[
                "Go to https://api.slack.com/apps",
                "Click 'Create New App'",
                "Choose 'From scratch'",
                "Enter an app name (e.g., 'fluxos Integration')",
                "Select your workspace",
                "Click 'Create App'",
            ],
            external_link="https://api.slack.com/apps",
            tips=["You'll be redirected to your app's configuration page"],
        ),
        SetupStep(
            step_number=2,
            title="Enable Incoming Webhooks",
            description="Activate the incoming webhooks feature for your app.",
            instructions=[
                "In the left sidebar, click 'Incoming Webhooks'",
                "Toggle 'Activate Incoming Webhooks' to ON",
                "Scroll down to see the 'Add New Webhook to Workspace' button",
            ],
        ),
        SetupStep(
            step_number=3,
            title="Add Webhook to Channel",
            description="Create a webhook URL for a specific channel.",
            instructions=[
                "Click 'Add New Webhook to Workspace'",
                "Select the channel where messages should be posted",
                "Click 'Allow' to authorize the webhook",
                "You'll be redirected back to the Incoming Webhooks page",
            ],
            tips=[
                "You can create multiple webhooks for different channels",
                "Each webhook is tied to one channel",
            ],
        ),
        SetupStep(
            step_number=4,
            title="Copy Webhook URL",
            description="Copy the webhook URL for your integration.",
            instructions=[
                "Find your new webhook in the 'Webhook URLs for Your Workspace' section",
                "Click 'Copy' next to the webhook URL",
                "The URL format is: https://hooks.slack.com/services/T.../B.../xxx",
            ],
            credential_type=CredentialType.webhook_url,
            tips=["Keep this URL private - treat it like a password"],
        ),
        SetupStep(
            step_number=5,
            title="(Optional) Get Signing Secret",
            description="For receiving events from Slack, you'll need the signing secret.",
            instructions=[
                "Go to 'Basic Information' in the left sidebar",
                "Scroll to 'App Credentials'",
                "Click 'Show' next to 'Signing Secret'",
                "Copy the signing secret",
            ],
            credential_type=CredentialType.webhook_secret,
            is_optional=True,
            tips=["Only needed if you want to receive events FROM Slack"],
        ),
        SetupStep(
            step_number=6,
            title="Configure in fluxos",
            description="Add your Slack credentials to fluxos.",
            instructions=[
                "Create a new Slack integration in fluxos",
                "Paste the webhook URL",
                "If using inbound events, add the signing secret",
                "Configure message settings and save",
            ],
        ),
    ],
    permissions_needed=[
        "incoming-webhook - Required for posting messages to channels",
        "chat:write - Required if using bot token instead of webhook",
    ],
    test_steps=[
        "Send a test message using the fluxos test feature",
        "Verify the message appears in the selected Slack channel",
        "Check message formatting (text, blocks) displays correctly",
    ],
    common_issues=[
        {
            "issue": "Webhook URL returns 'invalid_payload'",
            "solution": "Ensure your message JSON is properly formatted. The 'text' or 'blocks' field is required.",
        },
        {
            "issue": "Messages not posting to channel",
            "solution": "Verify the webhook hasn't been revoked. Check if the channel was deleted or renamed.",
        },
        {
            "issue": "App installation blocked by admin",
            "solution": "Contact your Slack workspace admin to approve the app installation.",
        },
        {
            "issue": "Rate limited by Slack",
            "solution": "Slack allows about 1 message per second per webhook. Use message batching or reduce frequency.",
        },
    ],
    video_tutorial_url="https://api.slack.com/tutorials/tracks/posting-messages-with-incoming-webhooks",
)


GITHUB_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.github,
    estimated_time_minutes=5,
    prerequisites=[
        "A GitHub account with access to the repository",
        "Admin access to repository settings (for webhooks)",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Create Personal Access Token (for outbound)",
            description="Generate a token to create issues and post comments.",
            instructions=[
                "Go to GitHub Settings > Developer settings > Personal access tokens",
                "Click 'Generate new token (classic)' or 'Fine-grained tokens'",
                "Give it a descriptive name (e.g., 'fluxos Integration')",
                "Select expiration (90 days recommended)",
                "Select scopes: 'repo' for full access or specific scopes",
                "Click 'Generate token'",
                "Copy the token immediately (you won't see it again)",
            ],
            external_link="https://github.com/settings/tokens",
            credential_type=CredentialType.api_key,
            tips=[
                "Fine-grained tokens offer more security with granular permissions",
                "Store the token securely - it grants access to your repositories",
            ],
        ),
        SetupStep(
            step_number=2,
            title="Navigate to Repository Webhooks (for inbound)",
            description="Access webhook settings for your repository.",
            instructions=[
                "Go to your repository on GitHub",
                "Click 'Settings' tab",
                "In the left sidebar, click 'Webhooks'",
                "Click 'Add webhook'",
            ],
            external_link="https://github.com",
            is_optional=True,
            tips=["You need admin access to the repository to add webhooks"],
        ),
        SetupStep(
            step_number=3,
            title="Configure Webhook Settings",
            description="Set up the webhook to receive events.",
            instructions=[
                "Get your webhook URL from fluxos (create integration first)",
                "Paste the fluxos webhook URL in 'Payload URL'",
                "Set Content type to 'application/json'",
                "Create a strong secret and enter it in 'Secret'",
                "Select events to trigger: 'Let me select individual events'",
                "Check the events you want (push, pull_request, issues, etc.)",
                "Ensure 'Active' is checked",
                "Click 'Add webhook'",
            ],
            credential_type=CredentialType.webhook_secret,
            is_optional=True,
        ),
        SetupStep(
            step_number=4,
            title="Configure in fluxos",
            description="Add your GitHub credentials to fluxos.",
            instructions=[
                "Create a new GitHub integration in fluxos",
                "Add your Personal Access Token for outbound actions",
                "Add the webhook secret for inbound events (if configured)",
                "Set up the inbound webhook path",
                "Save the integration",
            ],
        ),
        SetupStep(
            step_number=5,
            title="Update GitHub Webhook URL",
            description="Update GitHub webhook with the fluxos webhook URL.",
            instructions=[
                "Copy the webhook URL from your fluxos integration",
                "Go back to GitHub repository Settings > Webhooks",
                "Edit your webhook and update the Payload URL",
                "Save the webhook",
            ],
            is_optional=True,
        ),
    ],
    permissions_needed=[
        "repo - Full control of repositories (for creating issues, comments)",
        "read:org - Read organization membership (optional)",
        "admin:repo_hook - Manage webhooks (for repository owners)",
    ],
    test_steps=[
        "For outbound: Use fluxos to create a test issue in your repository",
        "For inbound: Push a commit or create an issue to trigger the webhook",
        "Check GitHub webhook delivery history for success/failure status",
        "Verify events appear in fluxos with correct payload",
    ],
    common_issues=[
        {
            "issue": "401 Unauthorized errors",
            "solution": "Your token may have expired or lacks required permissions. Generate a new token with correct scopes.",
        },
        {
            "issue": "Webhook signature verification fails",
            "solution": "Ensure the secret in fluxos matches exactly what you configured in GitHub.",
        },
        {
            "issue": "Not receiving webhook events",
            "solution": "Check GitHub webhook delivery log for errors. Verify the URL is correct and accessible.",
        },
        {
            "issue": "Rate limit exceeded",
            "solution": "GitHub allows 5000 requests/hour for authenticated requests. Reduce API calls or use caching.",
        },
    ],
    video_tutorial_url="https://docs.github.com/en/developers/webhooks-and-events/webhooks/creating-webhooks",
)


STRIPE_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.stripe,
    estimated_time_minutes=5,
    prerequisites=[
        "A Stripe account (test or live mode)",
        "Access to the Stripe Dashboard",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Access Stripe Webhooks",
            description="Navigate to the webhooks section in Stripe Dashboard.",
            instructions=[
                "Log in to your Stripe Dashboard",
                "Go to Developers > Webhooks",
                "Click 'Add endpoint' (or 'Add destination' in newer UI)",
            ],
            external_link="https://dashboard.stripe.com/webhooks",
        ),
        SetupStep(
            step_number=2,
            title="Create fluxos Integration First",
            description="Create the integration in fluxos to get the webhook URL.",
            instructions=[
                "Open fluxos and create a new Stripe integration",
                "Configure the inbound webhook settings",
                "Copy the generated webhook URL",
            ],
            tips=["You'll need this URL for the Stripe webhook configuration"],
        ),
        SetupStep(
            step_number=3,
            title="Configure Stripe Webhook Endpoint",
            description="Add the fluxos webhook URL to Stripe.",
            instructions=[
                "Paste the fluxos webhook URL in 'Endpoint URL'",
                "Select the events to listen for",
                "Recommended events: checkout.session.completed, payment_intent.succeeded, payment_intent.payment_failed, customer.subscription.created/updated/deleted",
                "Click 'Add endpoint'",
            ],
            tips=[
                "Start with fewer events and add more as needed",
                "Use test mode first to verify the integration works",
            ],
        ),
        SetupStep(
            step_number=4,
            title="Copy Signing Secret",
            description="Get the webhook signing secret for verification.",
            instructions=[
                "After creating the endpoint, click on it to view details",
                "Find 'Signing secret' section",
                "Click 'Reveal' to see the secret (starts with whsec_)",
                "Copy the signing secret",
            ],
            credential_type=CredentialType.webhook_secret,
            tips=["The signing secret is unique per webhook endpoint"],
        ),
        SetupStep(
            step_number=5,
            title="Update fluxos Integration",
            description="Add the signing secret to your fluxos integration.",
            instructions=[
                "Go back to your fluxos Stripe integration",
                "Add the webhook signing secret as a credential",
                "Save the integration",
            ],
        ),
        SetupStep(
            step_number=6,
            title="Test with Stripe CLI (Optional)",
            description="Use Stripe CLI for local testing and debugging.",
            instructions=[
                "Install Stripe CLI: https://stripe.com/docs/stripe-cli",
                "Run: stripe listen --forward-to localhost:8000/your-webhook-path",
                "Trigger test events: stripe trigger payment_intent.succeeded",
                "Verify events are received in fluxos",
            ],
            is_optional=True,
            external_link="https://stripe.com/docs/stripe-cli",
        ),
    ],
    permissions_needed=[
        "Webhook endpoints (read/write) - To create and manage webhooks",
        "View mode - Test mode for development, Live mode for production",
    ],
    test_steps=[
        "Click 'Send test webhook' in Stripe Dashboard for your endpoint",
        "Select an event type (e.g., payment_intent.succeeded)",
        "Verify the event appears in fluxos",
        "Check that signature verification passes (no 401 errors)",
    ],
    common_issues=[
        {
            "issue": "Signature verification failed",
            "solution": "Ensure you're using the correct signing secret. Each endpoint has its own unique secret.",
        },
        {
            "issue": "Webhook endpoint shows errors in Stripe",
            "solution": "Check the endpoint URL is accessible from the internet. Stripe will retry failed deliveries.",
        },
        {
            "issue": "Events not being received",
            "solution": "Verify the endpoint is enabled and listening for the correct event types.",
        },
        {
            "issue": "Test mode vs Live mode confusion",
            "solution": "Test mode webhooks only receive test events. Create a separate endpoint for live mode.",
        },
    ],
    video_tutorial_url="https://stripe.com/docs/webhooks/quickstart",
)


CUSTOM_WEBHOOK_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.custom_webhook,
    estimated_time_minutes=3,
    prerequisites=[
        "Knowledge of the external service's API/webhook format",
        "Access credentials for the target service (if required)",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Gather Endpoint Information",
            description="Collect the necessary information about your target endpoint.",
            instructions=[
                "Identify the webhook URL where you want to send data",
                "Note any required authentication (API key, Bearer token, etc.)",
                "Understand the expected payload format",
                "Check for any rate limits or restrictions",
            ],
            tips=["Consult the service's API documentation for exact requirements"],
        ),
        SetupStep(
            step_number=2,
            title="Create Custom Integration",
            description="Set up the custom webhook integration in fluxos.",
            instructions=[
                "Create a new integration with 'Custom Webhook' provider",
                "Set the direction based on your needs (inbound, outbound, or both)",
                "Give it a descriptive name",
            ],
        ),
        SetupStep(
            step_number=3,
            title="Configure Outbound (if sending webhooks)",
            description="Set up credentials for sending webhooks to external services.",
            instructions=[
                "Add the target webhook URL as a credential",
                "If API key authentication is needed, add an api_key credential",
                "If Bearer token is needed, add an oauth_token credential",
                "Add any custom headers in the credential metadata",
            ],
            credential_type=CredentialType.webhook_url,
            is_optional=True,
            tips=["You can also pass the URL dynamically in each action request"],
        ),
        SetupStep(
            step_number=4,
            title="Configure Inbound (if receiving webhooks)",
            description="Set up your webhook endpoint to receive external events.",
            instructions=[
                "Configure the inbound webhook settings",
                "Choose an authentication method (none, api_key, signature, bearer)",
                "If using signature verification, add a webhook_secret credential",
                "Set up event filters if you only want certain events",
                "Optionally add a Jinja2 transform template to normalize payloads",
            ],
            credential_type=CredentialType.webhook_secret,
            is_optional=True,
        ),
        SetupStep(
            step_number=5,
            title="Configure External Service",
            description="Update the external service to use your fluxos webhook.",
            instructions=[
                "Copy the webhook URL from your fluxos integration",
                "Add this URL to the external service's webhook/notification settings",
                "Configure any required authentication headers",
                "Select the events you want to receive",
            ],
            is_optional=True,
        ),
    ],
    permissions_needed=[
        "Varies by target service - check their documentation",
    ],
    test_steps=[
        "For outbound: Send a test request using the fluxos test feature",
        "For inbound: Trigger an event in the external service",
        "Verify the payload format matches expectations",
        "Check authentication is working (no 401/403 errors)",
    ],
    common_issues=[
        {
            "issue": "Connection refused or timeout",
            "solution": "Verify the target URL is correct and accessible. Check firewall rules.",
        },
        {
            "issue": "Authentication errors (401/403)",
            "solution": "Double-check your API key or token. Ensure headers are formatted correctly.",
        },
        {
            "issue": "Payload format errors",
            "solution": "Check that your payload matches the expected JSON structure for the target service.",
        },
        {
            "issue": "Signature verification failing",
            "solution": "Ensure the webhook secret matches exactly and the signature algorithm is correct (usually HMAC-SHA256).",
        },
    ],
)


TWITTER_SETUP_GUIDE = ProviderSetupGuide(
    provider=IntegrationProvider.twitter,
    estimated_time_minutes=2,
    prerequisites=[
        "A Twitter/X developer account with an OAuth 2.0 app configured",
        "OAuth 2.0 Client ID and Client Secret set in the fluxos environment",
    ],
    steps=[
        SetupStep(
            step_number=1,
            title="Create Integration",
            description="Create a new Twitter/X integration in fluxos.",
            instructions=[
                "Go to Settings > Integrations in fluxos",
                "Click 'Create' and select 'X (Twitter)' as the provider",
                "Choose 'Outbound' or 'Both' direction",
                "Give it a descriptive name (e.g., 'Company X Account')",
            ],
        ),
        SetupStep(
            step_number=2,
            title="Connect Your X Account",
            description="Authorize fluxos to post on your behalf via OAuth 2.0.",
            instructions=[
                "On the integration detail page, click 'Connect to X'",
                "You'll be redirected to X to authorize fluxos",
                "Review the permissions and click 'Authorize app'",
                "You'll be redirected back to fluxos automatically",
            ],
            credential_type=CredentialType.oauth_token,
            tips=[
                "Tokens are stored encrypted and can be revoked at any time",
                "You can disconnect and reconnect your account if needed",
            ],
        ),
    ],
    permissions_needed=[
        "tweet.read - Read tweets on your behalf",
        "tweet.write - Post and delete tweets on your behalf",
        "users.read - Read your profile information",
        "offline.access - Maintain access when you're not using the app",
    ],
    test_steps=[
        "After connecting, verify the status shows 'Connected'",
        "Use a workflow to send a test tweet",
        "Check your X profile to confirm the tweet was posted",
    ],
    common_issues=[
        {
            "issue": "OAuth authorization fails",
            "solution": "Ensure X_OAUTH2_CLIENT_ID and X_OAUTH2_CLIENT_SECRET are configured correctly in the fluxos environment.",
        },
        {
            "issue": "Token expired errors",
            "solution": "Use the 'Refresh' functionality or disconnect and reconnect your account.",
        },
        {
            "issue": "Rate limit exceeded",
            "solution": "X allows approximately 50 tweets per 15-minute window. Reduce posting frequency.",
        },
    ],
)


# =============================================================================
# Provider Definitions
# =============================================================================

DISCORD_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.discord,
    display_name="Discord",
    description="Send messages and embeds to Discord channels via webhooks",
    documentation_url="https://discord.com/developers/docs/resources/webhook",
    icon_url="https://assets-global.website-files.com/6257adef93867e50d84d30e2/636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.svg",
    supported_directions=[
        IntegrationDirection.outbound,
        IntegrationDirection.bidirectional,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.webhook_url,
            requirement=CredentialRequirement.required,
            description="Discord webhook URL for sending messages",
            example_format="https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN",
            validation_pattern=r"^https://discord\.com/api/webhooks/\d+/[\w-]+$",
            required_for_outbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.webhook_secret,
            requirement=CredentialRequirement.optional,
            description="Secret for verifying incoming Discord interactions",
            required_for_inbound=True,
        ),
    ],
    inbound_event_types=[
        InboundEventType(
            event_type="interaction",
            description="Discord interaction (slash command, button, etc.)",
            example_payload={"type": 2, "data": {"name": "command_name"}},
        ),
        InboundEventType(
            event_type="message",
            description="Discord message event (via bot)",
        ),
    ],
    outbound_actions=[
        OutboundActionDefinition(
            action_type=OutboundActionType.send_message,
            description="Send a plain text message to a Discord channel",
            required_params=["content"],
            optional_params=["username", "avatar_url", "thread_id"],
            rate_limit_recommendation={"requests": 30, "window_seconds": 60},
        ),
        OutboundActionDefinition(
            action_type=OutboundActionType.send_embed,
            description="Send a rich embed message with title, description, fields, and colors",
            required_params=[],  # At least title or description required
            optional_params=[
                "title", "description", "color", "fields", "footer_text",
                "footer_icon_url", "author_name", "author_url", "author_icon_url",
                "thumbnail_url", "image_url", "timestamp", "username", "avatar_url",
            ],
            rate_limit_recommendation={"requests": 30, "window_seconds": 60},
        ),
    ],
    validation_rules=[
        ValidationRule("content", "max_length", 2000, "Discord message content must be 2000 characters or less"),
        ValidationRule("title", "max_length", 256, "Discord embed title must be 256 characters or less"),
        ValidationRule("description", "max_length", 4096, "Discord embed description must be 4096 characters or less"),
        ValidationRule("fields", "max_items", 25, "Discord embed can have at most 25 fields"),
        ValidationRule("field.name", "max_length", 256, "Discord embed field name must be 256 characters or less"),
        ValidationRule("field.value", "max_length", 1024, "Discord embed field value must be 1024 characters or less"),
        ValidationRule("footer_text", "max_length", 2048, "Discord embed footer must be 2048 characters or less"),
        ValidationRule("author_name", "max_length", 256, "Discord embed author name must be 256 characters or less"),
    ],
    setup_guide=DISCORD_SETUP_GUIDE,
)


SLACK_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.slack,
    display_name="Slack",
    description="Send messages and Block Kit messages to Slack channels via webhooks or API",
    documentation_url="https://api.slack.com/messaging/webhooks",
    icon_url="https://a.slack-edge.com/80588/marketing/img/icons/icon_slack_hash_colored.png",
    supported_directions=[
        IntegrationDirection.inbound,
        IntegrationDirection.outbound,
        IntegrationDirection.bidirectional,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.webhook_url,
            requirement=CredentialRequirement.conditional,
            description="Slack incoming webhook URL for sending messages",
            example_format="https://hooks.slack.com/services/<workspace>/<channel>/<token>",
            validation_pattern=r"^https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[\w]+$",
            required_for_outbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.bot_token,
            requirement=CredentialRequirement.optional,
            description="Slack bot token for API access (xoxb-...)",
            example_format="xoxb-your-bot-token",
            validation_pattern=r"^xoxb-[\w-]+$",
        ),
        CredentialDefinition(
            credential_type=CredentialType.webhook_secret,
            requirement=CredentialRequirement.conditional,
            description="Slack signing secret for verifying incoming webhooks",
            required_for_inbound=True,
        ),
    ],
    inbound_event_types=[
        InboundEventType(
            event_type="message",
            description="Message posted in a channel",
            example_payload={"type": "message", "text": "Hello", "user": "U123"},
        ),
        InboundEventType(
            event_type="app_mention",
            description="Bot was mentioned in a channel",
        ),
        InboundEventType(
            event_type="reaction_added",
            description="Reaction emoji added to a message",
        ),
        InboundEventType(
            event_type="slash_command",
            description="User invoked a slash command",
        ),
        InboundEventType(
            event_type="interactive",
            description="User interacted with a button, menu, or modal",
        ),
    ],
    outbound_actions=[
        OutboundActionDefinition(
            action_type=OutboundActionType.send_message,
            description="Send a plain text message to a Slack channel",
            required_params=["content"],
            optional_params=["channel", "username", "icon_emoji", "icon_url", "thread_ts", "unfurl_links", "unfurl_media", "mrkdwn"],
            rate_limit_recommendation={"requests": 1, "window_seconds": 1},  # Slack recommends 1 msg/sec
        ),
        OutboundActionDefinition(
            action_type=OutboundActionType.send_blocks,
            description="Send a Block Kit formatted message with rich layout",
            required_params=["blocks"],
            optional_params=["text", "channel", "username", "icon_emoji", "icon_url", "thread_ts"],
            rate_limit_recommendation={"requests": 1, "window_seconds": 1},
        ),
    ],
    validation_rules=[
        ValidationRule("content", "max_length", 40000, "Slack message text must be 40000 characters or less"),
        ValidationRule("blocks", "max_items", 50, "Slack message can have at most 50 blocks"),
        ValidationRule("section.text", "max_length", 3000, "Slack section text must be 3000 characters or less"),
        ValidationRule("header.text", "max_length", 150, "Slack header text must be 150 characters or less"),
        ValidationRule("section.fields", "max_items", 10, "Slack section can have at most 10 fields"),
        ValidationRule("context.elements", "max_items", 10, "Slack context block can have at most 10 elements"),
        ValidationRule("actions.elements", "max_items", 25, "Slack actions block can have at most 25 elements"),
        ValidationRule("button.text", "max_length", 75, "Slack button text must be 75 characters or less"),
    ],
    setup_guide=SLACK_SETUP_GUIDE,
)


GITHUB_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.github,
    display_name="GitHub",
    description="Create issues, post comments, and receive webhook events from GitHub repositories",
    documentation_url="https://docs.github.com/en/developers/webhooks-and-events/webhooks",
    icon_url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
    supported_directions=[
        IntegrationDirection.inbound,
        IntegrationDirection.outbound,
        IntegrationDirection.bidirectional,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.api_key,
            requirement=CredentialRequirement.conditional,
            description="GitHub Personal Access Token (PAT) or Fine-grained token for API access",
            example_format="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx or github_pat_...",
            validation_pattern=r"^(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]+)$",
            required_for_outbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.webhook_secret,
            requirement=CredentialRequirement.conditional,
            description="Secret for verifying GitHub webhook signatures (X-Hub-Signature-256)",
            required_for_inbound=True,
        ),
    ],
    inbound_event_types=[
        InboundEventType(
            event_type="push",
            description="Code pushed to a repository",
            example_payload={"ref": "refs/heads/main", "commits": []},
        ),
        InboundEventType(
            event_type="pull_request",
            description="Pull request opened, closed, merged, etc.",
        ),
        InboundEventType(
            event_type="issues",
            description="Issue opened, closed, labeled, etc.",
        ),
        InboundEventType(
            event_type="issue_comment",
            description="Comment posted on an issue or pull request",
        ),
        InboundEventType(
            event_type="release",
            description="Release published, edited, or deleted",
        ),
        InboundEventType(
            event_type="workflow_run",
            description="GitHub Actions workflow run completed",
        ),
        InboundEventType(
            event_type="check_run",
            description="Check run created or completed",
        ),
        InboundEventType(
            event_type="deployment",
            description="Deployment created",
        ),
        InboundEventType(
            event_type="deployment_status",
            description="Deployment status changed",
        ),
    ],
    outbound_actions=[
        OutboundActionDefinition(
            action_type=OutboundActionType.create_issue,
            description="Create a new issue in a GitHub repository",
            required_params=["owner", "repo", "title"],
            optional_params=["body", "labels", "assignees", "milestone"],
            rate_limit_recommendation={"requests": 30, "window_seconds": 60},
        ),
        OutboundActionDefinition(
            action_type=OutboundActionType.post_comment,
            description="Post a comment on an issue or pull request",
            required_params=["owner", "repo", "issue_number", "body"],
            optional_params=[],
            rate_limit_recommendation={"requests": 30, "window_seconds": 60},
        ),
    ],
    validation_rules=[
        ValidationRule("title", "max_length", 256, "GitHub issue title should be concise"),
        ValidationRule("body", "max_length", 65536, "GitHub issue body must be 65536 characters or less"),
        ValidationRule("labels", "max_items", 100, "GitHub issue can have at most 100 labels"),
        ValidationRule("assignees", "max_items", 10, "GitHub issue can have at most 10 assignees"),
    ],
    setup_guide=GITHUB_SETUP_GUIDE,
)


STRIPE_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.stripe,
    display_name="Stripe",
    description="Receive payment and subscription webhook events from Stripe",
    documentation_url="https://stripe.com/docs/webhooks",
    icon_url="https://images.stripeassets.com/fzn2n1nzq965/HTTOloNPhisV9P4hlMPNA/cacf1bb88b9fc492dfad34378d844280/Stripe_icon_-_square.svg",
    supported_directions=[
        IntegrationDirection.inbound,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.webhook_secret,
            requirement=CredentialRequirement.required,
            description="Stripe webhook signing secret (whsec_...)",
            example_format="whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            validation_pattern=r"^whsec_[a-zA-Z0-9]+$",
            required_for_inbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.api_key,
            requirement=CredentialRequirement.optional,
            description="Stripe API key for retrieving event details (sk_live_... or sk_test_...)",
            example_format="your_stripe_api_key_here",
            validation_pattern=r"^sk_(live|test)_[a-zA-Z0-9]+$",
        ),
    ],
    inbound_event_types=[
        InboundEventType(
            event_type="checkout.session.completed",
            description="Checkout session completed successfully",
        ),
        InboundEventType(
            event_type="payment_intent.succeeded",
            description="Payment intent succeeded",
        ),
        InboundEventType(
            event_type="payment_intent.payment_failed",
            description="Payment intent failed",
        ),
        InboundEventType(
            event_type="customer.subscription.created",
            description="New subscription created",
        ),
        InboundEventType(
            event_type="customer.subscription.updated",
            description="Subscription updated",
        ),
        InboundEventType(
            event_type="customer.subscription.deleted",
            description="Subscription canceled or deleted",
        ),
        InboundEventType(
            event_type="invoice.paid",
            description="Invoice paid successfully",
        ),
        InboundEventType(
            event_type="invoice.payment_failed",
            description="Invoice payment failed",
        ),
        InboundEventType(
            event_type="customer.created",
            description="New customer created",
        ),
        InboundEventType(
            event_type="charge.succeeded",
            description="Charge succeeded",
        ),
        InboundEventType(
            event_type="charge.failed",
            description="Charge failed",
        ),
        InboundEventType(
            event_type="charge.refunded",
            description="Charge refunded",
        ),
    ],
    outbound_actions=[],  # Stripe is inbound-only in this integration model
    validation_rules=[],
    setup_guide=STRIPE_SETUP_GUIDE,
)


TWITTER_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.twitter,
    display_name="X (Twitter)",
    description="Post tweets and read timelines via X/Twitter OAuth 2.0",
    documentation_url="https://developer.x.com/en/docs/x-api",
    icon_url=None,
    supported_directions=[
        IntegrationDirection.outbound,
        IntegrationDirection.bidirectional,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.oauth_token,
            requirement=CredentialRequirement.required,
            description="OAuth 2.0 access token (auto-populated via Connect to X flow)",
            required_for_outbound=True,
        ),
    ],
    inbound_event_types=[],
    outbound_actions=[
        OutboundActionDefinition(
            action_type=OutboundActionType.send_message,
            description="Post a tweet (280 character limit)",
            required_params=["content"],
            optional_params=["reply_to_tweet_id", "media_ids"],
            rate_limit_recommendation={"requests": 50, "window_seconds": 900},
        ),
    ],
    validation_rules=[
        ValidationRule("content", "max_length", 280, "Tweet must be 280 characters or less"),
    ],
    setup_guide=TWITTER_SETUP_GUIDE,
)


CUSTOM_WEBHOOK_PROVIDER = ProviderDefinition(
    provider=IntegrationProvider.custom_webhook,
    display_name="Custom Webhook",
    description="Send and receive webhooks from custom HTTP endpoints",
    documentation_url=None,
    icon_url=None,
    supported_directions=[
        IntegrationDirection.inbound,
        IntegrationDirection.outbound,
        IntegrationDirection.bidirectional,
    ],
    credentials=[
        CredentialDefinition(
            credential_type=CredentialType.webhook_url,
            requirement=CredentialRequirement.conditional,
            description="Target webhook URL for outbound requests",
            example_format="https://your-service.com/webhook",
            required_for_outbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.api_key,
            requirement=CredentialRequirement.optional,
            description="API key for authenticating outbound requests",
        ),
        CredentialDefinition(
            credential_type=CredentialType.webhook_secret,
            requirement=CredentialRequirement.optional,
            description="Secret for verifying inbound webhook signatures",
            required_for_inbound=True,
        ),
        CredentialDefinition(
            credential_type=CredentialType.oauth_token,
            requirement=CredentialRequirement.optional,
            description="Bearer/OAuth token for authenticating outbound requests",
        ),
    ],
    inbound_event_types=[
        InboundEventType(
            event_type="custom",
            description="Custom event from external service (event_type extracted from payload)",
        ),
    ],
    outbound_actions=[
        OutboundActionDefinition(
            action_type=OutboundActionType.post,
            description="Send an HTTP POST request with JSON payload",
            required_params=["payload"],
            optional_params=["url", "headers"],
        ),
        OutboundActionDefinition(
            action_type=OutboundActionType.put,
            description="Send an HTTP PUT request with JSON payload",
            required_params=["payload"],
            optional_params=["url", "headers"],
        ),
        OutboundActionDefinition(
            action_type=OutboundActionType.send_message,
            description="Send a message as JSON (content or message field)",
            required_params=["content"],
            optional_params=["url", "headers"],
        ),
    ],
    validation_rules=[],
    setup_guide=CUSTOM_WEBHOOK_SETUP_GUIDE,
)


# =============================================================================
# Provider Registry
# =============================================================================

PROVIDER_DEFINITIONS: dict[IntegrationProvider, ProviderDefinition] = {
    IntegrationProvider.discord: DISCORD_PROVIDER,
    IntegrationProvider.slack: SLACK_PROVIDER,
    IntegrationProvider.github: GITHUB_PROVIDER,
    IntegrationProvider.stripe: STRIPE_PROVIDER,
    IntegrationProvider.twitter: TWITTER_PROVIDER,
    IntegrationProvider.custom_webhook: CUSTOM_WEBHOOK_PROVIDER,
}


def get_provider_definition(provider: IntegrationProvider) -> Optional[ProviderDefinition]:
    """Get the definition for a provider."""
    return PROVIDER_DEFINITIONS.get(provider)


def get_all_providers() -> list[ProviderDefinition]:
    """Get all provider definitions."""
    return list(PROVIDER_DEFINITIONS.values())


def get_provider_by_name(provider_name: str) -> Optional[ProviderDefinition]:
    """Get provider definition by name string."""
    try:
        provider = IntegrationProvider(provider_name)
        return PROVIDER_DEFINITIONS.get(provider)
    except ValueError:
        return None


def get_setup_guide_by_name(provider_name: str) -> Optional[ProviderSetupGuide]:
    """Get the setup guide for a provider by name string."""
    provider_def = get_provider_by_name(provider_name)
    if provider_def and provider_def.setup_guide:
        return provider_def.setup_guide
    return None
