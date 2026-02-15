"""Integration management plugins for webhook automation.

INT-018: These plugins now use Mimic for integration management.
Mimic is the central integration registry and gateway for all external
service connections (Discord, Slack, GitHub, Stripe, custom webhooks).

These plugins enable the TaskPlannerAgent to:
- Create integrations via Mimic
- Configure inbound webhooks
- Execute outbound actions (send messages, etc.)
- Link integrations to task templates for automation
"""

from typing import Dict, Any, Optional
import json
import structlog

from src.core.config import settings
from src.application.integrations import IntegrationUseCases
from src.infrastructure.integrations import MimicIntegrationAdapter

logger = structlog.get_logger(__name__)

_integration_use_cases: Optional[IntegrationUseCases] = None


def _get_integration_use_cases() -> IntegrationUseCases:
    global _integration_use_cases
    if _integration_use_cases is None:
        _integration_use_cases = IntegrationUseCases(
            integration_ops=MimicIntegrationAdapter()
        )
    return _integration_use_cases

# Note: Imports are done inside functions to avoid circular imports
# since the plugin registry is imported during app initialization


async def create_integration_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a webhook integration via Mimic.

    INT-018: Now creates integrations through Mimic instead of InkPass directly.

    Inputs:
        name: str - Integration name (e.g., "discord-messages")
        provider: str - Provider type (discord, slack, github, stripe, custom_webhook)
        direction: str - Direction (inbound, outbound, bidirectional), default "bidirectional"
        user_token: str - Bearer token for authentication

    Returns:
        integration_id: str
        webhook_url: str - Full URL for the webhook endpoint (if inbound configured)
        message: str
    """
    from mimic import (
        IntegrationProvider,
        IntegrationDirection,
        ServiceUnavailableError as MimicUnavailable,
        ValidationError as MimicValidation,
    )
    from mimic.models import IntegrationCreate

    name = inputs.get("name")
    provider = inputs.get("provider", "custom_webhook")
    direction = inputs.get("direction", "bidirectional")
    token = inputs.get("user_token")

    if not name:
        return {"error": "name is required", "success": False}
    if not token:
        return {"error": "user_token is required", "success": False}

    try:
        # Validate enums
        provider_enum = IntegrationProvider(provider)
        direction_enum = IntegrationDirection(direction)
    except ValueError as e:
        return {"error": f"Invalid provider or direction: {e}", "success": False}

    try:
        use_cases = _get_integration_use_cases()
        # Create integration via Mimic
        result = await use_cases.create_integration(
            data=IntegrationCreate(
                name=name,
                provider=provider_enum,
                direction=direction_enum,
            ),
            token=token,
        )

        logger.info(
            "Integration created via Mimic",
            integration_id=result.id,
            name=name,
            provider=provider,
        )

        # Build response
        response = {
            "success": True,
            "integration_id": result.id,
            "name": result.name,
            "provider": result.provider.value if hasattr(result.provider, 'value') else result.provider,
            "direction": result.direction.value if hasattr(result.direction, 'value') else result.direction,
            "message": f"Integration '{name}' created. Configure inbound/outbound settings as needed.",
        }

        return response

    except MimicValidation as e:
        logger.warning("Integration validation failed", error=str(e))
        return {"error": f"Validation error: {str(e)}", "success": False}

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"error": "Integration service unavailable. Please try again later.", "success": False}

    except Exception as e:
        logger.error("Failed to create integration", error=str(e))
        return {"error": f"Failed to create integration: {str(e)}", "success": False}


async def configure_inbound_webhook_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Configure inbound webhook for an integration.

    INT-018: Sets up the inbound webhook configuration via Mimic.

    Inputs:
        integration_id: str - The integration ID
        auth_method: str - Auth method (none, api_key, signature, bearer), default "api_key"
        event_filters: list[str] - Event types to accept (optional)
        user_token: str - Bearer token for authentication

    Returns:
        success: bool
        webhook_url: str - Full URL to send webhooks to
        webhook_path: str - Path portion of the webhook URL
    """
    from mimic import (
        ServiceUnavailableError as MimicUnavailable,
        ValidationError as MimicValidation,
        ResourceNotFoundError as MimicNotFound,
    )
    from mimic.models import InboundConfigCreate, InboundAuthMethod, DestinationService

    integration_id = inputs.get("integration_id")
    auth_method = inputs.get("auth_method", "api_key")
    event_filters = inputs.get("event_filters")
    token = inputs.get("user_token")

    if not integration_id:
        return {"error": "integration_id is required", "success": False}
    if not token:
        return {"error": "user_token is required", "success": False}

    try:
        auth_method_enum = InboundAuthMethod(auth_method)
    except ValueError:
        return {"error": f"Invalid auth_method: {auth_method}", "success": False}

    try:
        use_cases = _get_integration_use_cases()
        result = await use_cases.set_inbound_config(
            integration_id=integration_id,
            config=InboundConfigCreate(
                auth_method=auth_method_enum,
                event_filters=event_filters,
                destination_service=DestinationService.TENTACKL,
                destination_config={
                    "forward_to_event_bus": True,
                },
            ),
            token=token,
        )

        webhook_url = result.get("webhook_url", "")
        webhook_path = result.get("webhook_path", "")

        logger.info(
            "Inbound webhook configured via Mimic",
            integration_id=integration_id,
            webhook_path=webhook_path,
        )

        return {
            "success": True,
            "webhook_url": webhook_url,
            "webhook_path": webhook_path,
            "auth_method": auth_method,
            "message": f"Webhook configured. External services should POST to: {webhook_url}",
        }

    except MimicNotFound as e:
        return {"error": f"Integration not found: {integration_id}", "success": False}

    except MimicValidation as e:
        return {"error": f"Validation error: {str(e)}", "success": False}

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"error": "Integration service unavailable. Please try again later.", "success": False}

    except Exception as e:
        logger.error("Failed to configure inbound webhook", error=str(e))
        return {"error": f"Failed to configure webhook: {str(e)}", "success": False}


async def execute_outbound_action_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Execute an outbound action via an integration.

    INT-018: Uses Mimic to execute outbound actions like sending messages
    to Discord, Slack, GitHub, or custom webhooks.

    Inputs:
        integration_id: str - The integration ID
        action_type: str - Action type (send_message, send_embed, send_blocks, post, etc.)
        content: str - Message content (optional)
        title: str - Title for embeds (optional)
        description: str - Description for embeds (optional)
        payload: dict - Custom payload for webhook actions (optional)
        user_token: str - Bearer token for authentication

    Returns:
        success: bool
        result: dict - Action result from Mimic
        message: str
    """
    from mimic import (
        ServiceUnavailableError as MimicUnavailable,
        ValidationError as MimicValidation,
        ResourceNotFoundError as MimicNotFound,
        RateLimitError as MimicRateLimit,
    )

    integration_id = inputs.get("integration_id")
    action_type = inputs.get("action_type", "send_message")
    token = inputs.get("user_token")

    if not integration_id:
        return {"error": "integration_id is required", "success": False}
    if not token:
        return {"error": "user_token is required", "success": False}

    # Build action params from inputs
    params = {}
    for key in ["content", "title", "description", "color", "fields", "blocks", "payload", "url", "headers"]:
        if inputs.get(key) is not None:
            params[key] = inputs[key]

    try:
        use_cases = _get_integration_use_cases()
        result = await use_cases.execute_action(
            integration_id=integration_id,
            action_type=action_type,
            params=params,
            token=token,
        )

        logger.info(
            "Outbound action executed via Mimic",
            integration_id=integration_id,
            action_type=action_type,
            success=result.success,
        )

        return {
            "success": result.success,
            "result": result.model_dump() if hasattr(result, 'model_dump') else {},
            "message": f"Action '{action_type}' executed successfully" if result.success else "Action failed",
        }

    except MimicNotFound as e:
        return {"error": f"Integration not found: {integration_id}", "success": False}

    except MimicValidation as e:
        return {"error": f"Validation error: {str(e)}", "success": False}

    except MimicRateLimit as e:
        return {"error": f"Rate limit exceeded. Please try again later.", "success": False}

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"error": "Integration service unavailable. Please try again later.", "success": False}

    except Exception as e:
        logger.error("Failed to execute outbound action", error=str(e))
        return {"error": f"Failed to execute action: {str(e)}", "success": False}


async def link_webhook_to_template_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Link a webhook integration to a task template.

    Configures the integration to automatically create tasks from a template
    when events arrive. The goal can include ${event.data.xxx} placeholders
    that are substituted with actual event data.

    INT-018: Now stores the configuration in Mimic's destination_config.

    Inputs:
        integration_id: str - The integration ID
        template_id: str - The task template ID to instantiate
        goal_template: str - Goal with ${event.data.xxx} placeholders (optional)
        user_id: str - User ID for task ownership (optional)
        organization_id: str - Organization ID for task ownership (optional)
        user_token: str - Bearer token for authentication

    Returns:
        success: bool
        message: str
    """
    from mimic import (
        ServiceUnavailableError as MimicUnavailable,
        ValidationError as MimicValidation,
        ResourceNotFoundError as MimicNotFound,
    )
    from mimic.models import InboundConfigCreate, InboundAuthMethod, DestinationService

    integration_id = inputs.get("integration_id")
    template_id = inputs.get("template_id")
    goal_template = inputs.get("goal_template", "Process webhook event")
    user_id = inputs.get("user_id")
    organization_id = inputs.get("organization_id")
    token = inputs.get("user_token")

    if not integration_id:
        return {"success": False, "error": "integration_id is required"}
    if not template_id:
        return {"success": False, "error": "template_id is required"}
    if not token:
        return {"success": False, "error": "user_token is required"}

    try:
        use_cases = _get_integration_use_cases()
        # Get current inbound config
        try:
            current_config = await use_cases.get_inbound_config(
                integration_id=integration_id,
                token=token,
            )
            auth_method_value = current_config.get("auth_method", InboundAuthMethod.API_KEY)
            auth_method = InboundAuthMethod(auth_method_value)
        except MimicNotFound:
            # No inbound config yet, use default
            auth_method = InboundAuthMethod.API_KEY

        # Build destination config for task automation
        destination_config = {
            "forward_to_event_bus": True,
            "auto_create_task": True,
            "template_id": template_id,
            "goal_template": goal_template,
        }
        if user_id:
            destination_config["user_id"] = user_id
        if organization_id:
            destination_config["organization_id"] = organization_id

        # Update inbound config with template link
        result = await use_cases.set_inbound_config(
            integration_id=integration_id,
            config=InboundConfigCreate(
                auth_method=auth_method,
                destination_service=DestinationService.TENTACKL,
                destination_config=destination_config,
            ),
            token=token,
        )

        logger.info(
            "Webhook linked to template via Mimic",
            integration_id=integration_id,
            template_id=template_id,
            goal_template=goal_template,
        )

        return {
            "success": True,
            "message": f"Integration {integration_id} linked to template {template_id}. "
                       f"Incoming webhooks will now create tasks automatically.",
        }

    except MimicNotFound as e:
        return {"success": False, "error": f"Integration not found: {integration_id}"}

    except MimicValidation as e:
        return {"success": False, "error": f"Validation error: {str(e)}"}

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"success": False, "error": "Integration service unavailable. Please try again later."}

    except Exception as e:
        logger.error("Failed to link webhook to template", error=str(e))
        return {"success": False, "error": str(e)}


async def get_integration_status_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get the status and configuration of an integration.

    INT-018: Now fetches integration details from Mimic.

    Inputs:
        integration_id: str - The integration ID
        user_token: str - Bearer token for authentication

    Returns:
        success: bool
        integration: dict - Integration details including inbound/outbound config
    """
    from mimic import (
        ServiceUnavailableError as MimicUnavailable,
        ResourceNotFoundError as MimicNotFound,
    )

    integration_id = inputs.get("integration_id")
    token = inputs.get("user_token")

    if not integration_id:
        return {"success": False, "error": "integration_id is required"}
    if not token:
        return {"success": False, "error": "user_token is required"}

    try:
        use_cases = _get_integration_use_cases()
        result = await use_cases.get_integration(
            integration_id=integration_id,
            token=token,
        )

        # Extract template info from inbound config if present
        auto_create_task = False
        template_id = None
        goal_template = None

        if result.inbound_config and result.inbound_config.destination_config:
            dest_config = result.inbound_config.destination_config
            auto_create_task = dest_config.get("auto_create_task", False)
            template_id = dest_config.get("template_id")
            goal_template = dest_config.get("goal_template")

        return {
            "success": True,
            "integration": {
                "id": result.id,
                "name": result.name,
                "provider": result.provider.value if hasattr(result.provider, 'value') else result.provider,
                "direction": result.direction.value if hasattr(result.direction, 'value') else result.direction,
                "status": result.status.value if hasattr(result.status, 'value') else result.status,
                "webhook_url": result.inbound_config.webhook_url if result.inbound_config else None,
                "auto_create_task": auto_create_task,
                "template_id": template_id,
                "goal_template": goal_template,
                "created_at": result.created_at.isoformat() if result.created_at else None,
                "updated_at": result.updated_at.isoformat() if result.updated_at else None,
            },
        }

    except MimicNotFound:
        return {"success": False, "error": f"Integration {integration_id} not found"}

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"success": False, "error": "Integration service unavailable. Please try again later."}

    except Exception as e:
        logger.error("Failed to get integration status", error=str(e))
        return {"success": False, "error": str(e)}


async def list_integrations_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """List the user's existing integrations.

    Inputs:
        user_token: str - Bearer token for authentication
        provider: str - Optional filter by provider (discord, slack, github, stripe, custom_webhook)
        status: str - Optional filter by status (active, inactive)

    Returns:
        success: bool
        integrations: list - List of integration summaries
        total: int
    """
    from mimic import ServiceUnavailableError as MimicUnavailable

    token = inputs.get("user_token")
    if not token:
        return {"error": "user_token is required", "success": False}

    provider = inputs.get("provider")
    status = inputs.get("status")

    try:
        use_cases = _get_integration_use_cases()
        result = await use_cases.list_integrations(
            token=token,
            provider=provider,
            status=status,
        )

        integrations = []
        for item in result.items:
            integrations.append({
                "id": item.id,
                "name": item.name,
                "provider": item.provider,
                "direction": item.direction,
                "status": item.status,
                "created_at": item.created_at,
            })

        logger.info(
            "Integrations listed",
            total=result.total,
            provider=provider,
        )

        return {
            "success": True,
            "integrations": integrations,
            "total": result.total,
        }

    except MimicUnavailable as e:
        logger.error("Mimic service unavailable", error=str(e))
        return {"error": "Integration service unavailable. Please try again later.", "success": False}

    except Exception as e:
        logger.error("Failed to list integrations", error=str(e))
        return {"error": f"Failed to list integrations: {str(e)}", "success": False}


# Plugin definitions for registry
INTEGRATION_PLUGIN_DEFINITIONS = [
    {
        "name": "list_integrations",
        "description": "Lists the user's existing integrations (Discord, Slack, GitHub, Stripe, custom webhooks). Use this BEFORE execute_outbound_action to discover integration IDs. Always call this first when the user wants to send a message to an external service.",
        "handler": list_integrations_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication (from task context)",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional filter by provider: discord, slack, github, stripe, custom_webhook",
                    "enum": ["discord", "slack", "github", "stripe", "custom_webhook"],
                },
                "status": {
                    "type": "string",
                    "description": "Optional filter by status: active, inactive",
                    "enum": ["active", "inactive"],
                },
            },
            "required": ["user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "integrations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "provider": {"type": "string"},
                            "direction": {"type": "string"},
                            "status": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
    {
        "name": "create_integration",
        "description": "Creates an integration for receiving webhooks or sending outbound messages. Supports Discord, Slack, GitHub, Stripe, and custom webhooks. Use this when users want to connect external services.",
        "handler": create_integration_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Integration name (e.g., 'discord-bot', 'github-webhooks')",
                },
                "provider": {
                    "type": "string",
                    "description": "Provider type: discord, slack, github, stripe, custom_webhook",
                    "enum": ["discord", "slack", "github", "stripe", "custom_webhook"],
                },
                "direction": {
                    "type": "string",
                    "description": "Direction: inbound (receive only), outbound (send only), bidirectional",
                    "enum": ["inbound", "outbound", "bidirectional"],
                    "default": "bidirectional",
                },
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication (from task context)",
                },
            },
            "required": ["name", "user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "integration_id": {"type": "string"},
                "name": {"type": "string"},
                "provider": {"type": "string"},
                "direction": {"type": "string"},
                "message": {"type": "string"},
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
    {
        "name": "configure_inbound_webhook",
        "description": "Configures inbound webhook settings for an integration. Sets up authentication method and generates the webhook URL that external services should send events to.",
        "handler": configure_inbound_webhook_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "integration_id": {
                    "type": "string",
                    "description": "The integration ID from create_integration",
                },
                "auth_method": {
                    "type": "string",
                    "description": "Authentication method for webhooks",
                    "enum": ["none", "api_key", "signature", "bearer"],
                    "default": "api_key",
                },
                "event_filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of event types to accept (optional)",
                },
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication",
                },
            },
            "required": ["integration_id", "user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "webhook_url": {"type": "string"},
                "webhook_path": {"type": "string"},
                "auth_method": {"type": "string"},
                "message": {"type": "string"},
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
    {
        "name": "execute_outbound_action",
        "description": "Executes an outbound action through an integration (e.g., send a message to Discord, post to Slack, create a GitHub issue). Requires outbound config to be set up first.",
        "handler": execute_outbound_action_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "integration_id": {
                    "type": "string",
                    "description": "The integration ID",
                },
                "action_type": {
                    "type": "string",
                    "description": "Action type: send_message, send_embed, send_blocks, create_issue, post, put",
                },
                "content": {
                    "type": "string",
                    "description": "Message content (for send_message)",
                },
                "title": {
                    "type": "string",
                    "description": "Title for embeds or issues",
                },
                "description": {
                    "type": "string",
                    "description": "Description for embeds",
                },
                "payload": {
                    "type": "object",
                    "description": "Custom payload for webhook actions",
                },
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication",
                },
            },
            "required": ["integration_id", "action_type", "user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "result": {"type": "object"},
                "message": {"type": "string"},
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
    {
        "name": "link_webhook_to_template",
        "description": "Configures an integration's webhook to trigger a task template when events arrive. Events will automatically create tasks from the template with goal substitution. Use ${event.data.xxx} placeholders in goal_template to include webhook data.",
        "handler": link_webhook_to_template_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "integration_id": {
                    "type": "string",
                    "description": "The integration ID",
                },
                "template_id": {
                    "type": "string",
                    "description": "The task template ID to instantiate on webhook",
                },
                "goal_template": {
                    "type": "string",
                    "description": "Goal with ${event.data.xxx} placeholders (e.g., 'Process message from ${event.data.user}')",
                },
                "user_id": {
                    "type": "string",
                    "description": "User ID for task ownership (optional)",
                },
                "organization_id": {
                    "type": "string",
                    "description": "Organization ID for task ownership (optional)",
                },
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication",
                },
            },
            "required": ["integration_id", "template_id", "user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
    {
        "name": "get_integration_status",
        "description": "Get the status and configuration of an integration, including webhook URL and whether it's linked to a task template.",
        "handler": get_integration_status_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "integration_id": {
                    "type": "string",
                    "description": "The integration ID",
                },
                "user_token": {
                    "type": "string",
                    "description": "Bearer token for authentication",
                },
            },
            "required": ["integration_id", "user_token"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "integration": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "provider": {"type": "string"},
                        "direction": {"type": "string"},
                        "status": {"type": "string"},
                        "webhook_url": {"type": "string"},
                        "auto_create_task": {"type": "boolean"},
                        "template_id": {"type": "string"},
                        "goal_template": {"type": "string"},
                    },
                },
                "error": {"type": "string"},
            },
        },
        "category": "integration",
    },
]
