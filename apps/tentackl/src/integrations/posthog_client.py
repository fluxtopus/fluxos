"""PostHog analytics client for Tentackl."""

import posthog
import structlog
from typing import Optional, Dict, Any
from src.core.config import settings

logger = structlog.get_logger()


class PostHogClient:
    """Wrapper for PostHog analytics."""

    _instance: Optional["PostHogClient"] = None

    def __init__(self):
        self.enabled = settings.POSTHOG_ENABLED and bool(settings.POSTHOG_API_KEY)
        if self.enabled:
            posthog.api_key = settings.POSTHOG_API_KEY
            posthog.host = settings.POSTHOG_HOST
            logger.info("posthog_initialized", host=settings.POSTHOG_HOST)

    @classmethod
    def get_instance(cls) -> "PostHogClient":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: Optional[Dict[str, Any]] = None
    ):
        """Capture an analytics event."""
        if not self.enabled:
            return
        try:
            posthog.capture(distinct_id, event, properties or {})
        except Exception as e:
            logger.warning("posthog_capture_failed", error=str(e), event=event)

    def identify(
        self,
        distinct_id: str,
        properties: Optional[Dict[str, Any]] = None
    ):
        """Identify a user with properties."""
        if not self.enabled:
            return
        try:
            posthog.identify(distinct_id, properties or {})
        except Exception as e:
            logger.warning("posthog_identify_failed", error=str(e))

    def shutdown(self):
        """Flush and shutdown the PostHog client."""
        if self.enabled:
            posthog.shutdown()
            logger.info("posthog_shutdown")


# Singleton instance
posthog_client = PostHogClient.get_instance()
