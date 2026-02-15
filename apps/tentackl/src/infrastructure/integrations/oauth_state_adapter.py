"""Infrastructure adapter for integration OAuth state storage."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import redis.asyncio as redis

from src.core.config import settings
from src.domain.integrations import IntegrationOAuthStatePort


class IntegrationOAuthStateAdapter(IntegrationOAuthStatePort):
    """Adapter that stores OAuth state in Redis."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "integration_oauth_state:",
    ) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._key_prefix = key_prefix

    async def store_state(self, state: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        client = await redis.from_url(self._redis_url, db=0, decode_responses=True)
        try:
            payload = json.dumps(data)
            await client.setex(f"{self._key_prefix}{state}", ttl_seconds, payload)
        finally:
            await client.aclose()

    async def get_state(self, state: str) -> Optional[Dict[str, Any]]:
        client = await redis.from_url(self._redis_url, db=0, decode_responses=True)
        try:
            raw = await client.get(f"{self._key_prefix}{state}")
        finally:
            await client.aclose()

        if not raw:
            return None
        return json.loads(raw)

    async def delete_state(self, state: str) -> None:
        client = await redis.from_url(self._redis_url, db=0, decode_responses=True)
        try:
            await client.delete(f"{self._key_prefix}{state}")
        finally:
            await client.aclose()

    async def pop_state(self, state: str) -> Optional[Dict[str, Any]]:
        client = await redis.from_url(self._redis_url, db=0, decode_responses=True)
        try:
            raw = await client.get(f"{self._key_prefix}{state}")
            if not raw:
                return None
            await client.delete(f"{self._key_prefix}{state}")
        finally:
            await client.aclose()

        return json.loads(raw)
