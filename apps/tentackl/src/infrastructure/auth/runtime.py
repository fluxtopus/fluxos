"""Auth runtime composition for infrastructure-owned auth service.

This module creates the singleton auth service and chooses backend by config.
"""

import structlog

from src.infrastructure.auth.auth_service import AuthService
from src.infrastructure.auth.backend import AuthBackend

logger = structlog.get_logger(__name__)


def _create_auth_service() -> AuthService:
    """Create the auth service with the appropriate backend.

    Picks InkPassAuthBackend when INKPASS_URL is configured (non-empty),
    otherwise falls back to LocalAuthBackend for standalone mode.
    """
    from src.core.config import settings

    inkpass_url = settings.INKPASS_URL

    if inkpass_url:
        try:
            from src.infrastructure.auth.inkpass_backend import InkPassAuthBackend

            backend = InkPassAuthBackend()
            logger.info("Auth service using InkPass backend", inkpass_url=inkpass_url)
            return AuthService(backend)
        except Exception as e:
            logger.warning(
                "Failed to initialize InkPass backend, falling back to local",
                error=str(e),
            )

    from src.infrastructure.auth.local_backend import LocalAuthBackend

    backend = LocalAuthBackend()
    logger.info("Auth service using local backend (standalone mode)")
    return AuthService(backend)


# Singleton instance - created once at import time
auth_service: AuthService = _create_auth_service()

__all__ = [
    "auth_service",
    "AuthService",
    "AuthBackend",
]
