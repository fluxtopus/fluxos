"""Gmail plugin handlers."""

import base64
from typing import Any, Dict

import httpx
import structlog

from .constants import GMAIL_API_BASE
from .exceptions import GooglePluginError, GoogleOAuthError
from .oauth import get_valid_access_token
from .token_store import get_token_store

logger = structlog.get_logger()


def _parse_gmail_message(msg_data: Dict) -> Dict[str, Any]:
    """Parse a Gmail message into a simplified format."""
    headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

    # Extract body
    body = ""
    payload = msg_data.get("payload", {})

    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    elif "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                break

    return {
        "id": msg_data.get("id"),
        "thread_id": msg_data.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": msg_data.get("snippet", ""),
        "body": body,
        "labels": msg_data.get("labelIds", [])
    }


async def gmail_list_messages_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Gmail messages with optional filters and delta sync support.

    Inputs:
        user_id: User ID for OAuth tokens
        query: Gmail search query (e.g., "is:unread", "from:example@gmail.com")
        max_results: Maximum number of messages (default: 10, max: 100)
        include_body: Whether to fetch full message body (default: False)
        delta_only: If True, only fetch messages since last sync (default: False)
        mark_processed: If True, mark fetched message IDs as processed (default: False)

    Returns:
        Dictionary with list of messages
    """
    user_id = inputs.get("user_id")
    if not user_id:
        raise GooglePluginError("'user_id' is required")

    query = inputs.get("query", "")
    max_results = min(int(inputs.get("max_results", 10)), 100)
    include_body = inputs.get("include_body", False)
    delta_only = inputs.get("delta_only", False)
    mark_processed = inputs.get("mark_processed", False)

    token_store = get_token_store()

    try:
        access_token = await get_valid_access_token(user_id)

        # Build query with delta filter if requested
        final_query = query
        last_sync = None
        if delta_only:
            last_sync = await token_store.get_last_sync_timestamp(user_id)
            if last_sync:
                # Gmail uses epoch seconds for after: filter
                after_epoch = int(last_sync.timestamp())
                after_filter = f"after:{after_epoch}"
                final_query = f"{query} {after_filter}".strip()
                logger.info(
                    "Delta sync enabled",
                    user_id=user_id,
                    last_sync=last_sync.isoformat(),
                    after_epoch=after_epoch
                )
            else:
                logger.info("No previous sync, fetching all messages", user_id=user_id)

        # Get processed message IDs for filtering
        processed_ids = set()
        if delta_only or mark_processed:
            processed_ids = await token_store.get_processed_message_ids(user_id)

        # List messages
        async with httpx.AsyncClient() as client:
            params = {"maxResults": max_results}
            if final_query:
                params["q"] = final_query

            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )

            if response.status_code != 200:
                raise GooglePluginError(f"Gmail API error: {response.text}")

            data = response.json()

        messages = data.get("messages", [])

        # Filter out already processed messages
        if processed_ids and messages:
            original_count = len(messages)
            messages = [m for m in messages if m.get("id") not in processed_ids]
            skipped = original_count - len(messages)
            if skipped > 0:
                logger.info(
                    "Filtered already processed messages",
                    user_id=user_id,
                    skipped=skipped,
                    remaining=len(messages)
                )

        # Optionally fetch full message details
        new_message_ids = []
        if include_body and messages:
            detailed_messages = []
            async with httpx.AsyncClient() as client:
                for msg in messages[:max_results]:
                    response = await client.get(
                        f"{GMAIL_API_BASE}/users/me/messages/{msg['id']}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"format": "full"}
                    )
                    if response.status_code == 200:
                        parsed = _parse_gmail_message(response.json())
                        detailed_messages.append(parsed)
                        new_message_ids.append(msg['id'])
            messages = detailed_messages
        else:
            new_message_ids = [m.get("id") for m in messages if m.get("id")]

        # Mark messages as processed and update sync timestamp
        if mark_processed and new_message_ids:
            await token_store.add_processed_message_ids(user_id, new_message_ids)
            await token_store.set_last_sync_timestamp(user_id)
            logger.info(
                "Marked messages as processed",
                user_id=user_id,
                count=len(new_message_ids)
            )

        logger.info(
            "Listed Gmail messages",
            user_id=user_id,
            count=len(messages),
            query=final_query,
            delta_only=delta_only
        )

        return {
            "success": True,
            "messages": messages,
            "count": len(messages),
            "next_page_token": data.get("nextPageToken"),
            "delta_mode": delta_only,
            "last_sync": last_sync.isoformat() if last_sync else None
        }

    except GoogleOAuthError:
        raise
    except Exception as e:
        logger.error("Failed to list Gmail messages", error=str(e))
        raise GooglePluginError(f"Failed to list Gmail messages: {str(e)}")


async def gmail_get_message_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific Gmail message by ID.

    Inputs:
        user_id: User ID for OAuth tokens
        message_id: Gmail message ID

    Returns:
        Dictionary with message details
    """
    user_id = inputs.get("user_id")
    message_id = inputs.get("message_id")

    if not user_id:
        raise GooglePluginError("'user_id' is required")
    if not message_id:
        raise GooglePluginError("'message_id' is required")

    try:
        access_token = await get_valid_access_token(user_id)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"}
            )

            if response.status_code == 404:
                raise GooglePluginError(f"Message not found: {message_id}")
            if response.status_code != 200:
                raise GooglePluginError(f"Gmail API error: {response.text}")

            message = _parse_gmail_message(response.json())

        logger.info("Retrieved Gmail message", user_id=user_id, message_id=message_id)

        return {
            "success": True,
            "message": message
        }

    except GoogleOAuthError:
        raise
    except GooglePluginError:
        raise
    except Exception as e:
        logger.error("Failed to get Gmail message", error=str(e))
        raise GooglePluginError(f"Failed to get Gmail message: {str(e)}")


# Plugin definitions for Gmail handlers
GMAIL_PLUGIN_DEFINITIONS = [
    {
        "name": "gmail_list_messages",
        "description": "List Gmail messages with optional filters",
        "handler": gmail_list_messages_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10, "maximum": 100},
                "include_body": {"type": "boolean", "default": False}
            },
            "required": ["user_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "messages": {"type": "array"},
                "count": {"type": "integer"}
            }
        },
        "category": "google",
    },
    {
        "name": "gmail_get_message",
        "description": "Get a specific Gmail message by ID",
        "handler": gmail_get_message_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "message_id": {"type": "string"}
            },
            "required": ["user_id", "message_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "object"}
            }
        },
        "category": "google",
    },
]
