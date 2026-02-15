# REVIEW:
# - Behavior depends entirely on settings.CORS_ORIGINS; if empty/blank, cross-origin requests will fail silently.
"""CORS configuration for FastAPI applications."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings

# Explicit list of allowed HTTP methods (no wildcard)
ALLOWED_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]

# Explicit list of allowed request headers (no wildcard).
# Includes standard headers plus custom headers used by the frontend
# and external integrations (webhooks, rate limiting).
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "X-API-Key",
    "X-Webhook-Signature",
    "X-Webhook-Source",
    "X-Idempotency-Key",
    "X-Request-ID",
]


def configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI application.

    Reads allowed origins from CORS_ORIGINS environment variable.
    Set CORS_ORIGINS to a comma-separated list of allowed origins.

    Example:
        CORS_ORIGINS="https://fluxtopus.com,https://www.fluxtopus.com"

    Args:
        app: The FastAPI application instance
    """
    # Parse comma-separated origins from config
    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
