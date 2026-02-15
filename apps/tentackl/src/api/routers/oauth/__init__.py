# REVIEW:
# - Separate OAuth router namespace alongside integrations_oauth; unclear boundary between app OAuth and integration OAuth.
"""OAuth provider routers."""

from .google import router as google_router

__all__ = ["google_router"]
