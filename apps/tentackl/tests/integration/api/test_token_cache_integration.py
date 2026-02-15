"""Integration tests for token validation cache with real Redis."""

import pytest
import pytest_asyncio
import json
import os
import redis.asyncio as redis

from src.api.token_cache import TokenCache, CACHE_KEY_PREFIX


# Use a separate Redis DB for tests
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://redis:6379/7")


@pytest_asyncio.fixture
async def redis_client():
    """Create a Redis client for testing."""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        # Test connection
        await client.ping()
        yield client
    finally:
        # Cleanup: delete all test keys
        keys = await client.keys(f"{CACHE_KEY_PREFIX}*")
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest_asyncio.fixture
async def token_cache_with_test_redis():
    """Create a TokenCache configured to use test Redis DB."""
    cache = TokenCache()
    # Override Redis URL for testing
    original_redis = cache._redis
    cache._redis = await redis.from_url(TEST_REDIS_URL, decode_responses=True)

    try:
        yield cache
    finally:
        # Cleanup: delete all test keys and close
        if cache._redis:
            keys = await cache._redis.keys(f"{CACHE_KEY_PREFIX}*")
            if keys:
                await cache._redis.delete(*keys)
            await cache._redis.aclose()
        cache._redis = original_redis


class TestTokenCacheWithRealRedis:
    """Integration tests with actual Redis."""

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Verify we can connect to Redis."""
        result = await redis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, token_cache_with_test_redis):
        """Test basic set and get operations with real Redis."""
        cache = token_cache_with_test_redis
        token = "test_token_integration_123"
        user_data = {
            "id": "user-integration-1",
            "email": "integration@test.com",
            "organization_id": "org-789",
            "status": "active"
        }

        # Set the cache
        await cache.set(token, user_data)

        # Get should return the data
        result = await cache.get(token)
        assert result == user_data

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, token_cache_with_test_redis):
        """Test that non-existent keys return None."""
        cache = token_cache_with_test_redis
        token = "non_existent_token_xyz"

        result = await cache.get(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, token_cache_with_test_redis):
        """Test that invalidation removes the cached data."""
        cache = token_cache_with_test_redis
        token = "token_to_invalidate"
        user_data = {"id": "user-2", "email": "invalidate@test.com"}

        # Set cache
        await cache.set(token, user_data)

        # Verify it's cached
        result = await cache.get(token)
        assert result == user_data

        # Invalidate
        await cache.invalidate(token)

        # Should now return None
        result = await cache.get(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_ttl_is_set(self, token_cache_with_test_redis, redis_client):
        """Test that cached tokens have a TTL set."""
        cache = token_cache_with_test_redis
        token = "token_with_ttl"
        user_data = {"id": "user-ttl", "email": "ttl@test.com"}

        # Set the cache
        await cache.set(token, user_data)

        # Get the key and check TTL
        key = cache._token_key(token)
        ttl = await redis_client.ttl(key)

        # TTL should be positive (not -1 which means no TTL, or -2 which means doesn't exist)
        assert ttl > 0
        # TTL should be close to configured value (allowing for some test execution time)
        assert ttl <= 600  # CACHE_TTL_SECONDS default

    @pytest.mark.asyncio
    async def test_different_tokens_isolated(self, token_cache_with_test_redis):
        """Test that different tokens have isolated cache entries."""
        cache = token_cache_with_test_redis
        token1 = "token_user_one"
        token2 = "token_user_two"
        user1 = {"id": "user-1", "email": "one@test.com"}
        user2 = {"id": "user-2", "email": "two@test.com"}

        # Cache both tokens
        await cache.set(token1, user1)
        await cache.set(token2, user2)

        # Retrieve and verify isolation
        result1 = await cache.get(token1)
        result2 = await cache.get(token2)

        assert result1 == user1
        assert result2 == user2

    @pytest.mark.asyncio
    async def test_invalidate_only_affects_target_token(self, token_cache_with_test_redis):
        """Test that invalidating one token doesn't affect others."""
        cache = token_cache_with_test_redis
        token_keep = "token_to_keep"
        token_delete = "token_to_delete"
        user_keep = {"id": "keep", "email": "keep@test.com"}
        user_delete = {"id": "delete", "email": "delete@test.com"}

        # Cache both
        await cache.set(token_keep, user_keep)
        await cache.set(token_delete, user_delete)

        # Invalidate one
        await cache.invalidate(token_delete)

        # Verify results
        result_keep = await cache.get(token_keep)
        result_delete = await cache.get(token_delete)

        assert result_keep == user_keep
        assert result_delete is None

    @pytest.mark.asyncio
    async def test_cache_update_overwrites(self, token_cache_with_test_redis):
        """Test that setting a token again overwrites the old value."""
        cache = token_cache_with_test_redis
        token = "token_to_update"
        old_data = {"id": "old", "email": "old@test.com", "status": "inactive"}
        new_data = {"id": "old", "email": "old@test.com", "status": "active"}

        # Set initial value
        await cache.set(token, old_data)
        result = await cache.get(token)
        assert result["status"] == "inactive"

        # Update with new value
        await cache.set(token, new_data)
        result = await cache.get(token)
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_json_serialization_preserves_types(self, token_cache_with_test_redis):
        """Test that JSON serialization preserves data types correctly."""
        cache = token_cache_with_test_redis
        token = "token_with_types"
        user_data = {
            "id": "user-types",
            "email": "types@test.com",
            "organization_id": "org-123",
            "two_fa_enabled": True,
            "status": "active",
            "inkpass_validated": True,
            "login_count": 42
        }

        await cache.set(token, user_data)
        result = await cache.get(token)

        # Verify types are preserved
        assert result["two_fa_enabled"] is True
        assert result["inkpass_validated"] is True
        assert result["login_count"] == 42
        assert isinstance(result["login_count"], int)


class TestAuthMiddlewareCacheIntegration:
    """Test auth middleware integration with token cache."""

    @pytest.mark.asyncio
    async def test_cache_reduces_inkpass_calls(self, token_cache_with_test_redis):
        """Verify that caching reduces the number of InkPass calls."""
        from unittest.mock import AsyncMock, patch, MagicMock

        cache = token_cache_with_test_redis
        token = "bearer_token_for_caching"
        user_data = {
            "id": "cached-user",
            "email": "cached@test.com",
            "organization_id": "org-cached",
            "two_fa_enabled": False,
            "status": "active",
            "inkpass_validated": True
        }

        # Pre-populate cache
        await cache.set(token, user_data)

        # Mock InkPass call
        mock_inkpass = AsyncMock()

        with patch('src.api.auth_middleware.inkpass_validate_token', mock_inkpass):
            with patch('src.api.auth_middleware.token_cache', cache):
                # Import here to get patched version
                from src.api.auth_middleware import AuthMiddleware, AuthType

                middleware = AuthMiddleware()

                # Create mock request with Bearer token using MagicMock for headers
                mock_request = MagicMock()
                headers_dict = {"Authorization": f"Bearer {token}"}
                mock_request.headers = MagicMock()
                mock_request.headers.get = lambda key, default=None: headers_dict.get(key, default)
                mock_request.headers.__getitem__ = lambda self, key: headers_dict[key]

                # Authenticate - should use cache
                user, auth_type = await middleware.authenticate(mock_request)

                # InkPass should NOT have been called (cache hit)
                mock_inkpass.assert_not_called()

                # User should be returned from cache
                assert user is not None
                assert user.id == "cached-user"
                assert auth_type == AuthType.BEARER
