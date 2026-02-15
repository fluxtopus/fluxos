"""
Google Plugin Package for Tentackl workflows.

This package provides Gmail and Google Calendar operations including:
- OAuth 2.0 authentication flow
- Gmail message fetching and searching
- Google Calendar event CRUD operations
- Token refresh and management

Organized by service:
- oauth.py: OAuth flow and token management
- gmail.py: Gmail operations
- calendar.py: Google Calendar operations
- token_store.py: Redis-based token storage
- constants.py: API endpoints and scopes
- exceptions.py: Plugin-specific exceptions
"""

from .exceptions import GooglePluginError, GoogleOAuthError
from .constants import (
    GOOGLE_AUTH_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO_URL,
    GMAIL_API_BASE,
    CALENDAR_API_BASE,
    CALENDAR_ASSISTANT_SCOPES,
)
from .token_store import GoogleTokenStore, get_token_store
from .oauth import (
    google_oauth_start_handler,
    google_oauth_callback_handler,
    google_oauth_status_handler,
    get_valid_access_token,
    OAUTH_PLUGIN_DEFINITIONS,
)
from .gmail import (
    gmail_list_messages_handler,
    gmail_get_message_handler,
    GMAIL_PLUGIN_DEFINITIONS,
)
from .calendar import (
    calendar_list_events_handler,
    calendar_create_event_handler,
    calendar_check_conflicts_handler,
    CALENDAR_PLUGIN_DEFINITIONS,
)

# Combined plugin definitions for registry
GOOGLE_PLUGIN_DEFINITIONS = (
    OAUTH_PLUGIN_DEFINITIONS +
    GMAIL_PLUGIN_DEFINITIONS +
    CALENDAR_PLUGIN_DEFINITIONS
)

# Plugin handlers for explicit registration
PLUGIN_HANDLERS = {
    "google_oauth_start": google_oauth_start_handler,
    "google_oauth_callback": google_oauth_callback_handler,
    "google_oauth_status": google_oauth_status_handler,
    "gmail_list_messages": gmail_list_messages_handler,
    "gmail_get_message": gmail_get_message_handler,
    "calendar_list_events": calendar_list_events_handler,
    "calendar_create_event": calendar_create_event_handler,
    "calendar_check_conflicts": calendar_check_conflicts_handler,
}

__all__ = [
    # Exceptions
    "GooglePluginError",
    "GoogleOAuthError",
    # Constants
    "GOOGLE_AUTH_URL",
    "GOOGLE_TOKEN_URL",
    "GOOGLE_USERINFO_URL",
    "GMAIL_API_BASE",
    "CALENDAR_API_BASE",
    "CALENDAR_ASSISTANT_SCOPES",
    # Token store
    "GoogleTokenStore",
    "get_token_store",
    # OAuth handlers
    "google_oauth_start_handler",
    "google_oauth_callback_handler",
    "google_oauth_status_handler",
    "get_valid_access_token",
    # Gmail handlers
    "gmail_list_messages_handler",
    "gmail_get_message_handler",
    # Calendar handlers
    "calendar_list_events_handler",
    "calendar_create_event_handler",
    "calendar_check_conflicts_handler",
    # Plugin definitions
    "GOOGLE_PLUGIN_DEFINITIONS",
    "PLUGIN_HANDLERS",
    "OAUTH_PLUGIN_DEFINITIONS",
    "GMAIL_PLUGIN_DEFINITIONS",
    "CALENDAR_PLUGIN_DEFINITIONS",
]
