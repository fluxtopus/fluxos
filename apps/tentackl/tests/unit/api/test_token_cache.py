"""Unit tests for token validation cache."""

import pytest
import json
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock

from src.api.token_cache import TokenCache, CACHE_KEY_PREFIX, CACHE_TTL_SECONDS


class TestTokenCache:
    """Test suite for TokenCache class."""

    @pytest.fixture
    def token_cache(self):
        """Create a fresh TokenCache instance for each test."""
        return TokenCache()

    @pytest.fixture
    def sample_token(self):
        """Sample JWT token for testing."""
        return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.test"

    @pytest.fixture
    def sample_user_data(self):
        """Sample user data for caching."""
        return {
            "id": "user-123",
            "email": "test@example.com",
            "organization_id": "org-456",
            "two_fa_enabled": False,
            "status": "active",
            "inkpass_validated": True
        }

    def test_token_key_creates_hash(self, token_cache, sample_token):
        """Test that _token_key creates a proper hash key."""
        key = token_cache._token_key(sample_token)

        # Should have the correct prefix
        assert key.startswith(CACHE_KEY_PREFIX)

        # Should be a SHA256 hash (first 32 chars)
        expected_hash = hashlib.sha256(sample_token.encode()).hexdigest()[:32]
        assert key == f"{CACHE_KEY_PREFIX}{expected_hash}"

    def test_token_key_different_tokens_different_hashes(self, token_cache):
        """Test that different tokens produce different keys."""
        key1 = token_cache._token_key("token_one")
        key2 = token_cache._token_key("token_two")

        assert key1 != key2

    def test_token_key_same_token_same_hash(self, token_cache):
        """Test that same token always produces same key."""
        token = "consistent_token"
        key1 = token_cache._token_key(token)
        key2 = token_cache._token_key(token)

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_get_returns_none_on_cache_miss(self, token_cache, sample_token):
        """Test that get returns None when token is not cached."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            result = await token_cache.get(sample_token)

        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_returns_cached_data_on_hit(self, token_cache, sample_token, sample_user_data):
        """Test that get returns user data on cache hit."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(sample_user_data)

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            result = await token_cache.get(sample_token)

        assert result == sample_user_data

    @pytest.mark.asyncio
    async def test_get_returns_none_on_redis_error(self, token_cache, sample_token):
        """Test that get fails open on Redis errors."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            result = await token_cache.get(sample_token)

        # Should fail open - return None so caller falls back to InkPass
        assert result is None

    @pytest.mark.asyncio
    async def test_set_caches_data_with_ttl(self, token_cache, sample_token, sample_user_data):
        """Test that set caches user data with correct TTL."""
        mock_redis = AsyncMock()

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            await token_cache.set(sample_token, sample_user_data)

        # Verify setex was called with correct arguments
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        # First arg is the key
        key = call_args[0][0]
        assert key.startswith(CACHE_KEY_PREFIX)

        # Second arg is TTL
        ttl = call_args[0][1]
        assert ttl == CACHE_TTL_SECONDS

        # Third arg is JSON-serialized data
        data = call_args[0][2]
        assert json.loads(data) == sample_user_data

    @pytest.mark.asyncio
    async def test_set_handles_redis_error_gracefully(self, token_cache, sample_token, sample_user_data):
        """Test that set doesn't raise on Redis errors (non-blocking)."""
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis write failed")

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            # Should not raise
            await token_cache.set(sample_token, sample_user_data)

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self, token_cache, sample_token):
        """Test that invalidate removes token from cache."""
        mock_redis = AsyncMock()

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            await token_cache.invalidate(sample_token)

        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args
        key = call_args[0][0]
        assert key.startswith(CACHE_KEY_PREFIX)

    @pytest.mark.asyncio
    async def test_invalidate_handles_redis_error_gracefully(self, token_cache, sample_token):
        """Test that invalidate doesn't raise on Redis errors."""
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = Exception("Redis delete failed")

        with patch.object(token_cache, '_get_redis', return_value=mock_redis):
            # Should not raise
            await token_cache.invalidate(sample_token)

    @pytest.mark.asyncio
    async def test_close_closes_redis_connection(self, token_cache):
        """Test that close properly closes Redis connection."""
        mock_redis = AsyncMock()
        token_cache._redis = mock_redis

        await token_cache.close()

        mock_redis.aclose.assert_called_once()
        assert token_cache._redis is None

    @pytest.mark.asyncio
    async def test_close_handles_no_connection(self, token_cache):
        """Test that close handles case when no connection exists."""
        token_cache._redis = None

        # Should not raise
        await token_cache.close()


class TestTokenCacheIntegration:
    """Integration tests for TokenCache with real Redis mock patterns."""

    @pytest.mark.asyncio
    async def test_full_cache_cycle(self):
        """Test complete cache workflow: set, get, invalidate."""
        cache = TokenCache()
        token = "test_token_123"
        user_data = {"id": "user-1", "email": "test@test.com"}

        # Mock Redis
        storage = {}
        mock_redis = AsyncMock()

        async def mock_get(key):
            return storage.get(key)

        async def mock_setex(key, ttl, value):
            storage[key] = value

        async def mock_delete(key):
            storage.pop(key, None)

        mock_redis.get = mock_get
        mock_redis.setex = mock_setex
        mock_redis.delete = mock_delete

        with patch.object(cache, '_get_redis', return_value=mock_redis):
            # Initially cache miss
            result = await cache.get(token)
            assert result is None

            # Set cache
            await cache.set(token, user_data)

            # Now cache hit
            result = await cache.get(token)
            assert result == user_data

            # Invalidate
            await cache.invalidate(token)

            # Cache miss again
            result = await cache.get(token)
            assert result is None
