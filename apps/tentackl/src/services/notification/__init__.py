# REVIEW: Import-time try/except masks any ImportError (including dependency
# REVIEW: errors) and silently falls back to no-ops. Consider explicit feature
# REVIEW: flags or more specific error handling to avoid hiding real failures.
"""Notification services for Tentackl.

When Mimic is not available (standalone mode), exports no-op stubs.
"""

import structlog

logger = structlog.get_logger(__name__)

try:
    from src.infrastructure.notifications.mimic_client import (
        TentacklMimicClient,
        NotificationType,
        get_mimic_client,
    )

    __all__ = [
        "TentacklMimicClient",
        "NotificationType",
        "get_mimic_client",
    ]
except ImportError as e:
    logger.info("Mimic notification client not available (standalone mode)", reason=str(e))

    # Provide no-op stubs so consumers don't need to check availability
    TentacklMimicClient = None  # type: ignore[assignment, misc]
    NotificationType = None  # type: ignore[assignment, misc]

    def get_mimic_client():  # type: ignore[misc]
        return None

    __all__ = [
        "TentacklMimicClient",
        "NotificationType",
        "get_mimic_client",
    ]
