"""Unit tests for security-sensitive rate limiting behavior."""

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from src.middleware import rate_limiting


class _FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expirations = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, window: int) -> None:
        self.expirations[key] = window


def _make_request(ip: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [],
        "query_string": b"",
        "client": (ip, 12345),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforce_rate_limit_uses_identifier_in_key():
    fake_redis = _FakeRedis()
    previous_client = rate_limiting.redis_client
    rate_limiting.redis_client = fake_redis

    try:
        request = _make_request()
        await rate_limiting.enforce_rate_limit(
            request=request,
            key="auth:login",
            limit=10,
            window=60,
            identifier="User@Example.com",
        )
    finally:
        rate_limiting.redis_client = previous_client

    assert "rate_limit:auth:login:127.0.0.1:user@example.com" in fake_redis.counts


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforce_rate_limit_blocks_after_limit():
    fake_redis = _FakeRedis()
    previous_client = rate_limiting.redis_client
    rate_limiting.redis_client = fake_redis

    try:
        request = _make_request()
        await rate_limiting.enforce_rate_limit(request, "auth:login", limit=1, window=60, identifier="a@b.com")
        with pytest.raises(HTTPException) as exc_info:
            await rate_limiting.enforce_rate_limit(request, "auth:login", limit=1, window=60, identifier="a@b.com")
    finally:
        rate_limiting.redis_client = previous_client

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

