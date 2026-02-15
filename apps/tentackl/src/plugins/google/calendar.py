"""Google Calendar plugin handlers."""

from datetime import datetime, timedelta
from typing import Any, Dict

import httpx
import structlog

from .constants import CALENDAR_API_BASE
from .exceptions import GooglePluginError, GoogleOAuthError
from .oauth import get_valid_access_token

logger = structlog.get_logger()


def _parse_calendar_event(event: Dict) -> Dict[str, Any]:
    """Parse a Calendar event into a simplified format."""
    start = event.get("start", {})
    end = event.get("end", {})

    return {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "attendees": [a.get("email") for a in event.get("attendees", [])],
        "organizer": event.get("organizer", {}).get("email"),
        "status": event.get("status"),
        "html_link": event.get("htmlLink")
    }


async def calendar_list_events_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Google Calendar events.

    Inputs:
        user_id: User ID for OAuth tokens
        calendar_id: Calendar ID (default: "primary")
        time_min: Start time (ISO format, default: now)
        time_max: End time (ISO format, default: 7 days from now)
        max_results: Maximum number of events (default: 50)

    Returns:
        Dictionary with list of events
    """
    user_id = inputs.get("user_id")
    if not user_id:
        raise GooglePluginError("'user_id' is required")

    calendar_id = inputs.get("calendar_id", "primary")
    max_results = min(int(inputs.get("max_results", 50)), 250)

    # Default time range: now to 7 days from now
    now = datetime.utcnow()
    time_min = inputs.get("time_min", now.isoformat() + "Z")
    time_max = inputs.get("time_max", (now + timedelta(days=7)).isoformat() + "Z")

    try:
        access_token = await get_valid_access_token(user_id)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "maxResults": max_results,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "singleEvents": "true",
                    "orderBy": "startTime"
                }
            )

            if response.status_code != 200:
                raise GooglePluginError(f"Calendar API error: {response.text}")

            data = response.json()

        events = [_parse_calendar_event(e) for e in data.get("items", [])]

        logger.info(
            "Listed Calendar events",
            user_id=user_id,
            count=len(events)
        )

        return {
            "success": True,
            "events": events,
            "count": len(events)
        }

    except GoogleOAuthError:
        raise
    except Exception as e:
        logger.error("Failed to list Calendar events", error=str(e))
        raise GooglePluginError(f"Failed to list Calendar events: {str(e)}")


async def calendar_create_event_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a Google Calendar event.

    Inputs:
        user_id: User ID for OAuth tokens
        calendar_id: Calendar ID (default: "primary")
        summary: Event title (required)
        start: Start datetime ISO format (required)
        end: End datetime ISO format (required)
        description: Event description (optional)
        location: Event location (optional)
        attendees: List of attendee emails (optional)

    Returns:
        Dictionary with created event details
    """
    user_id = inputs.get("user_id")
    summary = inputs.get("summary")
    start = inputs.get("start")
    end = inputs.get("end")

    if not user_id:
        raise GooglePluginError("'user_id' is required")
    if not summary:
        raise GooglePluginError("'summary' is required")
    if not start:
        raise GooglePluginError("'start' is required")
    if not end:
        raise GooglePluginError("'end' is required")

    calendar_id = inputs.get("calendar_id", "primary")

    # Build event body
    event_body = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"}
    }

    if inputs.get("description"):
        event_body["description"] = inputs["description"]
    if inputs.get("location"):
        event_body["location"] = inputs["location"]
    if inputs.get("attendees"):
        event_body["attendees"] = [{"email": e} for e in inputs["attendees"]]

    try:
        access_token = await get_valid_access_token(user_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=event_body
            )

            if response.status_code not in [200, 201]:
                raise GooglePluginError(f"Calendar API error: {response.text}")

            event = _parse_calendar_event(response.json())

        logger.info(
            "Created Calendar event",
            user_id=user_id,
            event_id=event["id"],
            summary=summary
        )

        return {
            "success": True,
            "event": event
        }

    except GoogleOAuthError:
        raise
    except Exception as e:
        logger.error("Failed to create Calendar event", error=str(e))
        raise GooglePluginError(f"Failed to create Calendar event: {str(e)}")


async def calendar_check_conflicts_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check for conflicting events in a time range.

    Inputs:
        user_id: User ID for OAuth tokens
        calendar_id: Calendar ID (default: "primary")
        start: Start datetime ISO format (required)
        end: End datetime ISO format (required)

    Returns:
        Dictionary with conflict information
    """
    user_id = inputs.get("user_id")
    start = inputs.get("start")
    end = inputs.get("end")

    if not user_id:
        raise GooglePluginError("'user_id' is required")
    if not start:
        raise GooglePluginError("'start' is required")
    if not end:
        raise GooglePluginError("'end' is required")

    calendar_id = inputs.get("calendar_id", "primary")

    try:
        # Get events in the time range
        result = await calendar_list_events_handler({
            "user_id": user_id,
            "calendar_id": calendar_id,
            "time_min": start,
            "time_max": end,
            "max_results": 10
        })

        conflicts = result.get("events", [])
        has_conflicts = len(conflicts) > 0

        return {
            "success": True,
            "has_conflicts": has_conflicts,
            "conflict_count": len(conflicts),
            "conflicts": conflicts
        }

    except Exception as e:
        logger.error("Failed to check Calendar conflicts", error=str(e))
        raise GooglePluginError(f"Failed to check Calendar conflicts: {str(e)}")


# Plugin definitions for Calendar handlers
CALENDAR_PLUGIN_DEFINITIONS = [
    {
        "name": "calendar_list_events",
        "description": "List Google Calendar events in a time range",
        "handler": calendar_list_events_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "max_results": {"type": "integer", "default": 50}
            },
            "required": ["user_id"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "events": {"type": "array"},
                "count": {"type": "integer"}
            }
        },
        "category": "google",
    },
    {
        "name": "calendar_create_event",
        "description": "Create a Google Calendar event",
        "handler": calendar_create_event_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
                "summary": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["user_id", "summary", "start", "end"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "event": {"type": "object"}
            }
        },
        "category": "google",
    },
    {
        "name": "calendar_check_conflicts",
        "description": "Check for conflicting events in a time range",
        "handler": calendar_check_conflicts_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
                "start": {"type": "string"},
                "end": {"type": "string"}
            },
            "required": ["user_id", "start", "end"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "has_conflicts": {"type": "boolean"},
                "conflict_count": {"type": "integer"},
                "conflicts": {"type": "array"}
            }
        },
        "category": "google",
    },
]
