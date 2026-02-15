from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse
import httpx
import os
import redis.asyncio as redis_async

from src.application.allowed_hosts import AllowedHostUseCases
from src.infrastructure.allowed_hosts import AllowedHostServiceAdapter
from src.interfaces.database import Database
import structlog

logger = structlog.get_logger(__name__)

# Note: This plugin exports handlers for explicit registration in registry.py
# to avoid circular dependencies


class HttpPluginError(Exception):
    pass


class AllowedHostService:
    """Test helper service that delegates to allowed-host use cases."""

    def __init__(self, database: Database | None = None):
        db = database or Database()
        self._use_cases = AllowedHostUseCases(
            host_ops=AllowedHostServiceAdapter(db)
        )

    async def is_host_allowed(self, url: str, environment: str | None = None):
        return await self._use_cases.check_host_allowed(url=url, environment=environment)


async def _rate_limit(redis_url: str, key: str, max_calls: int, window_s: int) -> bool:
    r = await redis_async.from_url(redis_url, decode_responses=True)
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s)
        count, _ = await pipe.execute()
        return int(count) <= max_calls
    finally:
        await r.aclose()


async def http_request_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """HTTP request plugin with DB-based allowlist + basic rate limiting.

    Inputs:
      method: GET|POST|PUT|DELETE|PATCH (default GET)
      url: string (required)
      headers: dict (optional)
      params: dict (optional)
      body: dict or string (optional)
      timeout: seconds (default 15)
      rate_limit: { max_calls: int, window_s: int } (optional)

    Returns:
      { status, headers, json?, text? }
    """
    url = inputs.get("url")
    if not url or not isinstance(url, str):
        raise HttpPluginError("'url' is required")
    method = str(inputs.get("method", "GET")).upper()
    headers = inputs.get("headers") or {}
    params = inputs.get("params") or {}
    body = inputs.get("body")
    timeout = float(inputs.get("timeout", 15))
    verify = bool(inputs.get("verify", True))

    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Check DB-based allowlist (no fallback - DB is the source of truth)
    service = AllowedHostService()
    is_allowed, error_message = await service.is_host_allowed(url)
    if not is_allowed:
        raise HttpPluginError(error_message or f"Host '{host}' not allowed")

    # Rate limit
    rl = inputs.get("rate_limit") or {}
    max_calls = int(rl.get("max_calls", 0))
    window_s = int(rl.get("window_s", 60))
    if max_calls > 0:
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        ok = await _rate_limit(redis_url, f"tentackl:plugin:http:{host}:rl:{window_s}", max_calls, window_s)
        if not ok:
            raise HttpPluginError("Rate limit exceeded")

    async with httpx.AsyncClient(
        timeout=timeout,
        verify=verify,
        follow_redirects=False  # Explicit SSRF protection - prevent redirect-based attacks
    ) as client:
        try:
            resp = await client.request(method, url, headers=headers, params=params, json=body if isinstance(body, (dict, list)) else None, data=body if isinstance(body, (str, bytes)) else None)
        except httpx.HTTPError as e:
            raise HttpPluginError(str(e))

    content_type = resp.headers.get("content-type", "")
    result: Dict[str, Any] = {
        "status": resp.status_code,
        "headers": dict(resp.headers),
    }
    try:
        if "application/json" in content_type:
            result["json"] = resp.json()
        else:
            result["text"] = resp.text
    except Exception:
        result["text"] = resp.text

    return result


# Export plugin handler for explicit registration in registry.py
PLUGIN_HANDLERS = {
    "http": http_request_handler,
}

# Plugin metadata for registration
HTTP_PLUGIN_DEFINITION = {
    "name": "http",
    "description": "Perform HTTP requests with allowlist and rate limiting",
    "handler": http_request_handler,
    "inputs_schema": {
        "type": "object",
        "properties": {
            "method": {"type": "string"},
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "params": {"type": "object"},
            "body": {},
            "timeout": {"type": "number"},
            "verify": {"type": "boolean"},
            "rate_limit": {
                "type": "object",
                "properties": {"max_calls": {"type": "integer"}, "window_s": {"type": "integer"}},
            },
        },
        "required": ["url"],
    },
    "outputs_schema": {"type": "object"},
    "category": "network",
}
