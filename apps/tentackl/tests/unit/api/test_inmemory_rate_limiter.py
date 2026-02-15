"""Unit tests for in-memory rate limiter fallback (SEC-012)."""

import time
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.rate_limiter import (
    InMemoryRateLimiter,
    RateLimiter,
    rate_limiter,
    rate_limit_unauthenticated,
    rate_limit_playground,
    rate_limit_webhook,
)
from fastapi import Request, HTTPException


class TestInMemoryRateLimiter:
    """Test the InMemoryRateLimiter class directly."""

    def test_allows_request_within_limit(self):
        """First request should always be allowed."""
        limiter = InMemoryRateLimiter()
        assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is True

    def test_blocks_request_over_effective_limit(self):
        """Requests beyond effective_max (50% of max_requests) should be blocked."""
        limiter = InMemoryRateLimiter()
        # max_requests=10, effective_max = int(10 * 0.5) = 5
        for i in range(5):
            assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is True
        # 6th request should be blocked
        assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is False

    def test_restrictiveness_multiplier(self):
        """Effective limit should be 50% of configured max_requests."""
        limiter = InMemoryRateLimiter()
        # max_requests=20 -> effective_max = 10
        for i in range(10):
            assert limiter.check_rate_limit("key1", max_requests=20, window_seconds=60) is True
        assert limiter.check_rate_limit("key1", max_requests=20, window_seconds=60) is False

    def test_minimum_effective_limit_is_one(self):
        """Even with max_requests=1, effective_max should be at least 1."""
        limiter = InMemoryRateLimiter()
        # max_requests=1, effective_max = max(1, int(1 * 0.5)) = max(1, 0) = 1
        assert limiter.check_rate_limit("key1", max_requests=1, window_seconds=60) is True
        assert limiter.check_rate_limit("key1", max_requests=1, window_seconds=60) is False

    def test_different_keys_are_independent(self):
        """Rate limits should be tracked independently per key."""
        limiter = InMemoryRateLimiter()
        # Fill up key1 to its limit
        for i in range(5):
            limiter.check_rate_limit("key1", max_requests=10, window_seconds=60)
        assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is False

        # key2 should still be allowed
        assert limiter.check_rate_limit("key2", max_requests=10, window_seconds=60) is True

    def test_window_expiry(self):
        """Entries older than window_seconds should be expired."""
        limiter = InMemoryRateLimiter()
        # Use a very short window
        window = 0.1  # 100ms

        # Fill up to the effective limit (max_requests=4, effective=2)
        limiter.check_rate_limit("key1", max_requests=4, window_seconds=window)
        limiter.check_rate_limit("key1", max_requests=4, window_seconds=window)
        assert limiter.check_rate_limit("key1", max_requests=4, window_seconds=window) is False

        # Wait for the window to expire
        time.sleep(0.15)

        # Should be allowed again
        assert limiter.check_rate_limit("key1", max_requests=4, window_seconds=window) is True

    def test_reset_clears_all_counters(self):
        """reset() should clear all tracked keys."""
        limiter = InMemoryRateLimiter()
        # Fill up a key
        for i in range(5):
            limiter.check_rate_limit("key1", max_requests=10, window_seconds=60)
        assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is False

        # Reset and try again
        limiter.reset()
        assert limiter.check_rate_limit("key1", max_requests=10, window_seconds=60) is True

    def test_cleanup_removes_stale_keys(self):
        """Cleanup should remove keys with no recent entries."""
        limiter = InMemoryRateLimiter()
        # Force a very short cleanup interval for testing
        limiter.CLEANUP_INTERVAL_SECONDS = 0

        # Add an entry
        limiter.check_rate_limit("key1", max_requests=10, window_seconds=0.05)

        # Wait for it to become stale (but the key remains because cleanup hasn't run)
        time.sleep(0.1)

        # Manually set timestamps to be old enough for cleanup
        with limiter._lock:
            limiter._counters["old_key"] = [time.monotonic() - 400]
            limiter._last_cleanup = 0  # Force cleanup on next check

        # Trigger a check that will run cleanup
        limiter.check_rate_limit("new_key", max_requests=10, window_seconds=60)

        # old_key should have been cleaned up (its entry is >300s old)
        with limiter._lock:
            assert "old_key" not in limiter._counters

    def test_concurrent_safety(self):
        """Multiple threads should be able to use the limiter safely."""
        import threading

        limiter = InMemoryRateLimiter()
        results = []
        errors = []

        def worker():
            try:
                for _ in range(20):
                    result = limiter.check_rate_limit("shared_key", max_requests=200, window_seconds=60)
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # effective_max = 100, total attempts = 100
        # First 100 should succeed, rest should fail
        assert sum(1 for r in results if r is True) == 100
        assert sum(1 for r in results if r is False) == 0


class TestRateLimiterRedisFailover:
    """Test that RateLimiter falls back to in-memory when Redis fails."""

    @pytest_asyncio.fixture
    async def limiter(self):
        """Create a rate limiter with a fresh in-memory fallback."""
        rl = RateLimiter(redis_url="redis://localhost:6379/15")
        # Reset the class-level fallback to avoid cross-test contamination
        RateLimiter._memory_fallback = InMemoryRateLimiter()
        return rl

    @pytest.mark.asyncio
    async def test_falls_back_to_memory_on_redis_error(self, limiter):
        """When Redis raises an exception, in-memory fallback should be used."""
        async def mock_get_redis():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis is down")
            return mock

        with patch.object(limiter, '_get_redis', mock_get_redis):
            # First request should be allowed via fallback
            result = await limiter.check_rate_limit(
                key="test_key", max_requests=10, window_seconds=60
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_fallback_is_more_restrictive(self, limiter):
        """In-memory fallback should allow only 50% of configured max_requests."""
        async def mock_get_redis():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis is down")
            return mock

        with patch.object(limiter, '_get_redis', mock_get_redis):
            # max_requests=10, effective fallback limit = 5
            results = []
            for i in range(7):
                result = await limiter.check_rate_limit(
                    key="test_key", max_requests=10, window_seconds=60
                )
                results.append(result)

            # First 5 should be True, last 2 should be False
            assert results == [True, True, True, True, True, False, False]

    @pytest.mark.asyncio
    async def test_fallback_does_not_fail_open(self, limiter):
        """Verify the old fail-open behavior is gone — Redis failures should NOT allow all requests."""
        async def mock_get_redis():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis is down")
            return mock

        with patch.object(limiter, '_get_redis', mock_get_redis):
            # Send 20 requests with max_requests=4 (effective=2)
            results = []
            for _ in range(20):
                result = await limiter.check_rate_limit(
                    key="test_key", max_requests=4, window_seconds=60
                )
                results.append(result)

            allowed = sum(1 for r in results if r is True)
            blocked = sum(1 for r in results if r is False)

            # Only 2 should be allowed (50% of 4)
            assert allowed == 2
            assert blocked == 18

    @pytest.mark.asyncio
    async def test_fallback_logs_warning(self, limiter):
        """Redis failure should log a warning about using fallback."""
        async def mock_get_redis():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis is down")
            return mock

        with patch.object(limiter, '_get_redis', mock_get_redis), \
             patch("src.api.rate_limiter.logger") as mock_logger:
            await limiter.check_rate_limit(
                key="test_key", max_requests=10, window_seconds=60
            )
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "in-memory fallback" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_redis_success_does_not_use_fallback(self, limiter):
        """When Redis works, in-memory fallback should NOT be consulted."""
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.zadd = MagicMock(return_value=pipe_mock)
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 5, 1, True])
        redis_mock.pipeline.return_value = pipe_mock

        async def mock_get_redis():
            return redis_mock

        with patch.object(limiter, '_get_redis', mock_get_redis), \
             patch.object(limiter._memory_fallback, 'check_rate_limit') as mock_mem:
            result = await limiter.check_rate_limit(
                key="test_key", max_requests=10, window_seconds=60
            )
            assert result is True
            # In-memory fallback should NOT have been called
            mock_mem.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_shared_across_instances(self):
        """All RateLimiter instances should share the same in-memory fallback."""
        RateLimiter._memory_fallback = InMemoryRateLimiter()
        rl1 = RateLimiter()
        rl2 = RateLimiter()
        assert rl1._memory_fallback is rl2._memory_fallback


class TestDependencyFallbackIntegration:
    """Test that dependency functions correctly use the fallback via check_rate_limit."""

    @pytest.fixture(autouse=True)
    def reset_fallback(self):
        """Reset the class-level fallback before each test."""
        RateLimiter._memory_fallback = InMemoryRateLimiter()

    @pytest.mark.asyncio
    async def test_unauthenticated_rate_limit_with_redis_down(self):
        """rate_limit_unauthenticated should block after effective limit when Redis is down."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_user = None
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def mock_redis_fail():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis down")
            return mock

        dependency = rate_limit_unauthenticated(max_requests=4, window_seconds=60)

        with patch.object(rate_limiter, '_get_redis', mock_redis_fail):
            # effective_max = 2 (50% of 4)
            await dependency(request)  # 1st - allowed
            await dependency(request)  # 2nd - allowed

            # 3rd should be blocked
            with pytest.raises(HTTPException) as exc_info:
                await dependency(request)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_playground_rate_limit_with_redis_down(self):
        """rate_limit_playground should block after effective limit when Redis is down."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.url = MagicMock()
        request.url.path = "/playground/plan"

        async def mock_redis_fail():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis down")
            return mock

        dependency = rate_limit_playground(max_requests=6, window_seconds=60)

        with patch.object(rate_limiter, '_get_redis', mock_redis_fail):
            # effective_max = 3 (50% of 6)
            await dependency(request)  # 1st
            await dependency(request)  # 2nd
            await dependency(request)  # 3rd

            # 4th should be blocked
            with pytest.raises(HTTPException) as exc_info:
                await dependency(request)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_webhook_rate_limit_with_redis_down(self):
        """rate_limit_webhook should block after effective limit when Redis is down."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.path_params = {"source_id": "test-source"}

        async def mock_redis_fail():
            mock = MagicMock()
            mock.pipeline.side_effect = ConnectionError("Redis down")
            return mock

        dependency = rate_limit_webhook(max_requests=4, window_seconds=60)

        with patch.object(rate_limiter, '_get_redis', mock_redis_fail):
            # effective_max = 2 (50% of 4)
            await dependency(request)  # 1st
            await dependency(request)  # 2nd

            # 3rd should be blocked
            with pytest.raises(HTTPException) as exc_info:
                await dependency(request)
            assert exc_info.value.status_code == 429


class TestSourceCodeVerification:
    """Verify the rate limiter source code no longer fails open."""

    def test_no_fail_open_comment(self):
        """The 'Fail open' comment should be replaced."""
        import inspect
        source = inspect.getsource(RateLimiter.check_rate_limit)
        assert "fail open" not in source.lower()
        assert "allow request if rate limiting fails" not in source.lower()

    def test_fallback_call_in_except_block(self):
        """The except block should call in-memory fallback, not return True."""
        import inspect
        source = inspect.getsource(RateLimiter.check_rate_limit)
        assert "_memory_fallback.check_rate_limit" in source

    def test_inmemory_class_exists(self):
        """InMemoryRateLimiter class should exist and be importable."""
        assert hasattr(InMemoryRateLimiter, 'check_rate_limit')
        assert hasattr(InMemoryRateLimiter, '_cleanup')
        assert hasattr(InMemoryRateLimiter, 'reset')
        assert hasattr(InMemoryRateLimiter, 'RESTRICTIVENESS_MULTIPLIER')

    def test_restrictiveness_multiplier_is_strict(self):
        """The multiplier should be less than 1.0 (more restrictive)."""
        assert InMemoryRateLimiter.RESTRICTIVENESS_MULTIPLIER < 1.0
        assert InMemoryRateLimiter.RESTRICTIVENESS_MULTIPLIER > 0.0
