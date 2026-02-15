# REVIEW:
# - DEBUG flag is read at import time from env; diverges from settings and won't reflect runtime config changes.
"""Safe error message helpers to prevent information leakage.

In production, error messages should not expose internal architecture,
file paths, or implementation details. This module provides helpers
to return safe, generic error messages in production while allowing
detailed errors in debug mode.
"""

import os

# Debug mode flag - only show detailed errors when explicitly enabled
DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def safe_error_detail(
    internal_message: str,
    user_message: str = "An internal error occurred. Please try again later."
) -> str:
    """
    Return detailed error in debug mode, generic message in production.

    Args:
        internal_message: The detailed internal error (for logging/debugging)
        user_message: The safe message to show users in production

    Returns:
        The appropriate message based on DEBUG setting
    """
    return internal_message if DEBUG else user_message


def safe_validation_error(
    internal_message: str,
    user_message: str = "Invalid request. Please check your input."
) -> str:
    """
    Return detailed validation error in debug mode.

    Args:
        internal_message: The detailed validation error
        user_message: The safe message for production

    Returns:
        The appropriate message based on DEBUG setting
    """
    return internal_message if DEBUG else user_message


def safe_auth_error(
    internal_message: str,
    user_message: str = "Authentication failed."
) -> str:
    """
    Return safe authentication error.

    Args:
        internal_message: The detailed auth error (e.g., "Token expired", "Invalid signature")
        user_message: The safe message for production

    Returns:
        The appropriate message based on DEBUG setting
    """
    return internal_message if DEBUG else user_message
