"""Google OAuth token storage using Redis."""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - handled at runtime if dependency missing
    Fernet = None
    InvalidToken = Exception

logger = structlog.get_logger()


class GoogleTokenStore:
    """
    Simple token storage using Redis.

    Stores OAuth tokens per user with:
    - Access token (encrypted, short-lived)
    - Refresh token (encrypted, long-lived)
    - Token expiry timestamp
    """

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._redis = None
        self._fernet = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def _get_fernet(self):
        """Get Fernet cipher for token encryption."""
        if self._fernet is not None:
            return self._fernet
        if Fernet is None:
            raise RuntimeError("cryptography dependency is required for token encryption")

        key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
        if not key:
            raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY is required for token encryption")

        self._fernet = Fernet(key.encode())
        return self._fernet

    def _encrypt_token(self, value: str) -> str:
        if not value:
            return ""
        cipher = self._get_fernet()
        encrypted = cipher.encrypt(value.encode()).decode()
        return f"enc:{encrypted}"

    def _decrypt_token(self, value: str) -> str:
        if not value:
            return ""
        # Backward compatibility for legacy plaintext values.
        if not value.startswith("enc:"):
            return value

        cipher = self._get_fernet()
        try:
            return cipher.decrypt(value[4:].encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Failed to decrypt stored Google OAuth token") from exc

    async def store_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int
    ) -> None:
        """Store OAuth tokens for a user."""
        redis = await self._get_redis()
        key = f"google_oauth:{user_id}"

        data = {
            "access_token": self._encrypt_token(access_token),
            "refresh_token": self._encrypt_token(refresh_token),
            "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "encryption": "fernet",
        }

        await redis.hset(key, mapping=data)
        # Set expiry to 1 year (refresh token validity)
        await redis.expire(key, 365 * 24 * 60 * 60)

        logger.info("Stored Google OAuth tokens", user_id=user_id)

    async def get_tokens(self, user_id: str) -> Optional[Dict[str, str]]:
        """Get OAuth tokens for a user."""
        redis = await self._get_redis()
        key = f"google_oauth:{user_id}"

        data = await redis.hgetall(key)
        if not data:
            return None

        access_token = self._decrypt_token(data.get("access_token", ""))
        refresh_token = self._decrypt_token(data.get("refresh_token", ""))
        data["access_token"] = access_token
        data["refresh_token"] = refresh_token

        return data

    async def is_token_expired(self, user_id: str, buffer_seconds: int = 300) -> bool:
        """Check if access token is expired or about to expire."""
        tokens = await self.get_tokens(user_id)
        if not tokens or "expires_at" not in tokens:
            return True

        expires_at = datetime.fromisoformat(tokens["expires_at"])
        threshold = datetime.utcnow() + timedelta(seconds=buffer_seconds)

        return expires_at <= threshold

    async def delete_tokens(self, user_id: str) -> None:
        """Delete OAuth tokens for a user."""
        redis = await self._get_redis()
        key = f"google_oauth:{user_id}"
        await redis.delete(key)
        logger.info("Deleted Google OAuth tokens", user_id=user_id)

    # ============== Delta Sync Tracking ==============

    async def get_last_sync_timestamp(self, user_id: str) -> Optional[datetime]:
        """Get the timestamp of the last email sync for delta fetching."""
        redis = await self._get_redis()
        key = f"google_calendar_assistant:{user_id}:last_sync"
        timestamp = await redis.get(key)
        if timestamp:
            return datetime.fromisoformat(timestamp)
        return None

    async def set_last_sync_timestamp(self, user_id: str, timestamp: datetime = None) -> None:
        """Set the timestamp of the last email sync."""
        redis = await self._get_redis()
        key = f"google_calendar_assistant:{user_id}:last_sync"
        ts = timestamp or datetime.utcnow()
        await redis.set(key, ts.isoformat())
        logger.debug("Updated last sync timestamp", user_id=user_id, timestamp=ts.isoformat())

    async def get_processed_message_ids(self, user_id: str, limit: int = 100) -> set:
        """Get set of already processed message IDs to avoid duplicates."""
        redis = await self._get_redis()
        key = f"google_calendar_assistant:{user_id}:processed_ids"
        ids = await redis.smembers(key)
        return set(ids) if ids else set()

    async def add_processed_message_ids(self, user_id: str, message_ids: List[str]) -> None:
        """Mark message IDs as processed."""
        if not message_ids:
            return
        redis = await self._get_redis()
        key = f"google_calendar_assistant:{user_id}:processed_ids"
        await redis.sadd(key, *message_ids)
        # Keep only last 1000 IDs to prevent unbounded growth
        await redis.expire(key, 30 * 24 * 60 * 60)  # 30 days
        logger.debug("Added processed message IDs", user_id=user_id, count=len(message_ids))

    async def get_calendar_assistant_state(self, user_id: str) -> Dict[str, Any]:
        """Get full calendar assistant state for a user."""
        redis = await self._get_redis()
        state_key = f"google_calendar_assistant:{user_id}:state"
        state = await redis.hgetall(state_key)
        return state or {}

    async def update_calendar_assistant_state(self, user_id: str, updates: Dict[str, Any]) -> None:
        """Update calendar assistant state."""
        redis = await self._get_redis()
        state_key = f"google_calendar_assistant:{user_id}:state"
        string_updates = {k: str(v) for k, v in updates.items()}
        await redis.hset(state_key, mapping=string_updates)

    async def store_oauth_state_nonce(
        self,
        nonce: str,
        user_id: str,
        ttl_seconds: int = 600,
    ) -> None:
        """Store OAuth nonce for replay protection."""
        redis = await self._get_redis()
        key = f"google_oauth_state_nonce:{nonce}"
        await redis.setex(key, ttl_seconds, user_id)

    async def consume_oauth_state_nonce(self, nonce: str, user_id: str) -> bool:
        """Consume OAuth nonce once. Returns False for replay/invalid nonce."""
        redis = await self._get_redis()
        key = f"google_oauth_state_nonce:{nonce}"
        stored = await redis.get(key)
        if not stored or stored != user_id:
            return False

        await redis.delete(key)
        return True


# Singleton token store
_token_store: Optional[GoogleTokenStore] = None


def get_token_store() -> GoogleTokenStore:
    """Get or create token store singleton."""
    global _token_store
    if _token_store is None:
        _token_store = GoogleTokenStore()
    return _token_store
