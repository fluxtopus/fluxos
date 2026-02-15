"""Discord Followup Plugin

Plugin for sending follow-up responses to Discord interactions (slash commands).

This plugin uses Discord's interaction webhook endpoint which:
1. Uses the interaction token (no bot credentials needed for followup)
2. Sends responses to the same channel/thread where the command was invoked
3. Has a 15-minute validity window for the interaction token

Usage in workflow steps:
```yaml
- name: send_response
  plugin:
    name: discord_followup
  inputs:
    application_id: "${trigger_event.metadata.application_id}"
    interaction_token: "${trigger_event.metadata.interaction_token}"
    content: "${generate_joke.output.result}"
```
"""

from typing import Dict, Any, Optional, List
import httpx
import structlog

logger = structlog.get_logger(__name__)

# Plugin definitions for registry
DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS = [
    {
        "name": "discord_followup",
        "description": "Send a followup message to a Discord interaction (slash command response)",
        "handler": None,  # Will be set below
        "inputs_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Discord application ID"},
                "interaction_token": {"type": "string", "description": "Interaction token from slash command (15 min validity)"},
                "content": {"type": "string", "description": "Message content to send"},
                "embeds": {"type": "array", "description": "Optional Discord embed objects"},
                "tts": {"type": "boolean", "description": "Text-to-speech flag"},
                "timeout": {"type": "number", "description": "Request timeout in seconds"}
            },
            "required": ["application_id", "interaction_token"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message_id": {"type": "string"},
                "content": {"type": "string"},
                "error": {"type": "string"}
            }
        },
        "category": "integration"
    },
    {
        "name": "discord_edit_followup",
        "description": "Edit an existing Discord followup message",
        "handler": None,  # Will be set below
        "inputs_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "interaction_token": {"type": "string"},
                "message_id": {"type": "string"},
                "content": {"type": "string"},
                "embeds": {"type": "array"}
            },
            "required": ["application_id", "interaction_token", "message_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message_id": {"type": "string"},
                "error": {"type": "string"}
            }
        },
        "category": "integration"
    },
    {
        "name": "discord_delete_followup",
        "description": "Delete a Discord followup message",
        "handler": None,  # Will be set below
        "inputs_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "interaction_token": {"type": "string"},
                "message_id": {"type": "string"}
            },
            "required": ["application_id", "interaction_token", "message_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "error": {"type": "string"}
            }
        },
        "category": "integration"
    }
]

DISCORD_API_BASE = "https://discord.com/api/v10"


async def discord_followup_handler(inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Send a followup message to a Discord interaction.

    Inputs:
        application_id: str - Discord application ID (required)
        interaction_token: str - Interaction token from slash command (required, 15 min validity)
        content: str - Message content (required unless embeds provided)
        embeds: list - Optional list of Discord embed objects
        tts: bool - Optional text-to-speech flag
        timeout: float - Request timeout in seconds (default 15)

    Returns:
        success: bool
        message_id: str (if successful)
        content: str (the content sent)
        error: str (if failed)
    """
    application_id = inputs.get("application_id")
    interaction_token = inputs.get("interaction_token")
    content = inputs.get("content")
    embeds = inputs.get("embeds")
    tts = inputs.get("tts", False)
    timeout = float(inputs.get("timeout", 15))

    # Validate required fields
    if not application_id:
        return {"success": False, "error": "Missing required input: application_id"}

    if not interaction_token:
        return {"success": False, "error": "Missing required input: interaction_token"}

    if not content and not embeds:
        return {"success": False, "error": "Must provide either content or embeds"}

    # Build the followup webhook URL
    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}"

    # Build the payload
    payload: Dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    if tts:
        payload["tts"] = True

    logger.info(
        "Sending Discord followup message",
        application_id=application_id,
        token_preview=interaction_token[:20] + "..." if len(interaction_token) > 20 else interaction_token,
        has_content=bool(content),
        embed_count=len(embeds) if embeds else 0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code in [200, 201, 204]:
                message_id = None
                if response.content:
                    try:
                        result_data = response.json()
                        message_id = result_data.get("id")
                    except Exception:
                        pass

                logger.info(
                    "Discord followup sent successfully",
                    message_id=message_id,
                    application_id=application_id,
                )

                return {
                    "success": True,
                    "message_id": message_id,
                    "content": content,
                }
            else:
                error_text = response.text
                try:
                    error_data = response.json()
                    error_message = error_data.get("message", error_text)
                except Exception:
                    error_message = error_text

                logger.error(
                    "Discord followup failed",
                    status_code=response.status_code,
                    error=error_message,
                    application_id=application_id,
                )

                return {
                    "success": False,
                    "error": f"Discord API error ({response.status_code}): {error_message}"
                }

    except httpx.TimeoutException:
        logger.error("Discord followup timed out", application_id=application_id, timeout=timeout)
        return {"success": False, "error": f"Request timed out after {timeout} seconds"}

    except Exception as e:
        logger.error("Discord followup exception", application_id=application_id, error=str(e), exc_info=True)
        return {"success": False, "error": str(e)}


async def discord_edit_followup_handler(inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Edit an existing Discord followup message.

    Inputs:
        application_id: str - Discord application ID (required)
        interaction_token: str - Interaction token (required)
        message_id: str - ID of message to edit (required)
        content: str - New content (optional)
        embeds: list - New embeds (optional)
        timeout: float - Request timeout in seconds (default 15)

    Returns:
        success: bool
        message_id: str
        error: str (if failed)
    """
    application_id = inputs.get("application_id")
    interaction_token = inputs.get("interaction_token")
    message_id = inputs.get("message_id")
    content = inputs.get("content")
    embeds = inputs.get("embeds")
    timeout = float(inputs.get("timeout", 15))

    if not all([application_id, interaction_token, message_id]):
        return {"success": False, "error": "Missing required inputs: application_id, interaction_token, message_id"}

    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}/messages/{message_id}"

    payload: Dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    if embeds is not None:
        payload["embeds"] = embeds

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.patch(url, json=payload)

            if response.status_code == 200:
                logger.info("Discord followup edited", message_id=message_id)
                return {"success": True, "message_id": message_id}
            else:
                error_text = response.text
                logger.error("Failed to edit Discord followup", status_code=response.status_code, error=error_text)
                return {"success": False, "error": error_text}

    except Exception as e:
        logger.error("Exception editing Discord followup", error=str(e))
        return {"success": False, "error": str(e)}


async def discord_delete_followup_handler(inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Delete a Discord followup message.

    Inputs:
        application_id: str - Discord application ID (required)
        interaction_token: str - Interaction token (required)
        message_id: str - ID of message to delete (required)
        timeout: float - Request timeout in seconds (default 15)

    Returns:
        success: bool
        error: str (if failed)
    """
    application_id = inputs.get("application_id")
    interaction_token = inputs.get("interaction_token")
    message_id = inputs.get("message_id")
    timeout = float(inputs.get("timeout", 15))

    if not all([application_id, interaction_token, message_id]):
        return {"success": False, "error": "Missing required inputs: application_id, interaction_token, message_id"}

    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}/messages/{message_id}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.delete(url)

            if response.status_code == 204:
                logger.info("Discord followup deleted", message_id=message_id)
                return {"success": True}
            else:
                error_text = response.text
                logger.error("Failed to delete Discord followup", status_code=response.status_code, error=error_text)
                return {"success": False, "error": error_text}

    except Exception as e:
        logger.error("Exception deleting Discord followup", error=str(e))
        return {"success": False, "error": str(e)}


# Set handlers in definitions
DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS[0]["handler"] = discord_followup_handler
DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS[1]["handler"] = discord_edit_followup_handler
DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS[2]["handler"] = discord_delete_followup_handler
