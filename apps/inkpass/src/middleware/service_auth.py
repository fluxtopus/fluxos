"""Service-to-service API key authentication helpers."""

import hmac
from typing import Callable, Optional

from fastapi import Header, HTTPException, status

from src.config import settings


def _parse_service_keys() -> list[tuple[str, str]]:
    """Parse SERVICE_API_KEYS from config into (service, key) pairs."""
    pairs: list[tuple[str, str]] = []
    if not settings.SERVICE_API_KEYS:
        return pairs

    for raw_pair in settings.SERVICE_API_KEYS.split(","):
        pair = raw_pair.strip()
        if ":" not in pair:
            continue
        service, key = pair.split(":", 1)
        service = service.strip()
        key = key.strip()
        if service and key:
            pairs.append((service, key))

    return pairs


def _resolve_service_name(presented_key: str) -> Optional[str]:
    """Resolve service name for a presented key using constant-time comparison."""
    for service, configured_key in _parse_service_keys():
        if hmac.compare_digest(presented_key, configured_key):
            return service
    return None


def require_service_api_key(allowed_services: Optional[set[str]] = None) -> Callable:
    """Dependency factory that requires a valid X-Service-API-Key header."""

    def _dependency(x_service_api_key: Optional[str] = Header(None, alias="X-Service-API-Key")) -> str:
        if not x_service_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Service-API-Key header",
            )

        service_name = _resolve_service_name(x_service_api_key)
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service API key",
            )

        if allowed_services and service_name not in allowed_services:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Service is not allowed to access this endpoint",
            )

        return service_name

    return _dependency

