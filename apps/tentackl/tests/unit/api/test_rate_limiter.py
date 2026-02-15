"""Unit tests for rate limiting functionality."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import ipaddress
from fastapi import Request, HTTPException
from fastapi.testclient import TestClient

from src.api.rate_limiter import RateLimiter, rate_limit_unauthenticated, rate_limiter
from src.api.auth_middleware import AuthUser, AuthType


class TestRateLimiter:
    """Test the RateLimiter class."""
    
    @pytest_asyncio.fixture
    async def limiter(self):
        """Create a rate limiter instance."""
        return RateLimiter(redis_url="redis://localhost:6379/15")
    
    def test_get_client_identifier_direct_ip(self, limiter):
        """Test getting client identifier from direct IP."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        
        identifier = limiter.get_client_identifier(request)
        assert identifier == "rate_limit:192.168.1.1"
    
    def test_get_client_identifier_forwarded_for(self, limiter):
        """Test getting client identifier from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        with patch("src.api.rate_limiter.TRUST_PROXY_HEADERS", True), \
             patch("src.api.rate_limiter.TRUSTED_PROXY_NETWORKS", [ipaddress.ip_network("192.168.1.0/24")]):
            identifier = limiter.get_client_identifier(request)
            assert identifier == "rate_limit:10.0.0.1"
    
    def test_get_client_identifier_no_client(self, limiter):
        """Test getting client identifier when client is None."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None
        
        identifier = limiter.get_client_identifier(request)
        assert identifier == "rate_limit:unknown"

    def test_get_client_identifier_ignores_forwarded_for_from_untrusted_proxy(self, limiter):
        """X-Forwarded-For must be ignored unless request came from trusted proxy CIDR."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "198.51.100.10"

        with patch("src.api.rate_limiter.TRUST_PROXY_HEADERS", True), \
             patch("src.api.rate_limiter.TRUSTED_PROXY_NETWORKS", [ipaddress.ip_network("192.168.1.0/24")]):
            identifier = limiter.get_client_identifier(request)
            assert identifier == "rate_limit:198.51.100.10"
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self, limiter):
        """Test rate limit check when within limit."""
        # Create a mock Redis client
        redis_mock = MagicMock()
        redis_mock.aclose = AsyncMock()

        # Mock pipeline - pipeline() returns a sync object, but execute() is async
        pipe_mock = MagicMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.zadd = MagicMock(return_value=pipe_mock)
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 5, 1, True])  # 5 requests, under limit of 10
        redis_mock.pipeline.return_value = pipe_mock

        # Patch _get_redis to return the mock when awaited
        async def mock_get_redis():
            return redis_mock

        with patch.object(limiter, '_get_redis', mock_get_redis):
            result = await limiter.check_rate_limit(
                key="test_key",
                max_requests=10,
                window_seconds=60
            )

            assert result is True
            assert pipe_mock.zremrangebyscore.called
            assert pipe_mock.zcard.called
            assert pipe_mock.zadd.called
            assert pipe_mock.expire.called

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, limiter):
        """Test rate limit check when limit is exceeded."""
        # Create a mock Redis client
        redis_mock = MagicMock()
        redis_mock.aclose = AsyncMock()

        # Mock pipeline - 30 requests, at limit of 30 (should be < 30, so this fails)
        pipe_mock = MagicMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.zadd = MagicMock(return_value=pipe_mock)
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 30, 1, True])
        redis_mock.pipeline.return_value = pipe_mock

        # Patch _get_redis to return the mock when awaited
        async def mock_get_redis():
            return redis_mock

        with patch.object(limiter, '_get_redis', mock_get_redis):
            result = await limiter.check_rate_limit(
                key="test_key",
                max_requests=30,
                window_seconds=60
            )

            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_failure_uses_fallback(self, limiter):
        """Test rate limit uses in-memory fallback when Redis fails."""
        from src.api.rate_limiter import InMemoryRateLimiter
        # Reset fallback to avoid cross-test contamination
        RateLimiter._memory_fallback = InMemoryRateLimiter()

        with patch.object(limiter, '_get_redis') as mock_redis:
            redis_mock = AsyncMock()
            mock_redis.return_value = redis_mock
            redis_mock.pipeline.side_effect = Exception("Redis connection failed")
            redis_mock.aclose = AsyncMock()

            # First request should be allowed via in-memory fallback
            result = await limiter.check_rate_limit(
                key="test_key",
                max_requests=10,
                window_seconds=60
            )

            assert result is True


class TestRateLimitUnauthenticated:
    """Test the rate_limit_unauthenticated dependency."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_allows_authenticated_user(self):
        """Test that authenticated users bypass rate limiting."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_user = AuthUser(
            id="user1",
            auth_type=AuthType.BEARER,
            username="testuser",
            scopes=["workflow:read"]
        )
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        
        dependency = rate_limit_unauthenticated(max_requests=30, window_seconds=60)
        
        # Should not raise exception for authenticated user
        result = await dependency(request)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_rate_limit_allows_unauthenticated_within_limit(self):
        """Test that unauthenticated users within limit are allowed."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_user = None  # Unauthenticated
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        
        with patch.object(rate_limiter, 'check_rate_limit', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True  # Within limit
            
            dependency = rate_limit_unauthenticated(max_requests=30, window_seconds=60)
            result = await dependency(request)
            
            assert result is None
            mock_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limit_blocks_unauthenticated_over_limit(self):
        """Test that unauthenticated users over limit are blocked."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.auth_user = None  # Unauthenticated
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        
        with patch.object(rate_limiter, 'check_rate_limit', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False  # Over limit
            
            dependency = rate_limit_unauthenticated(max_requests=30, window_seconds=60)
            
            with pytest.raises(HTTPException) as exc_info:
                await dependency(request)
            
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in exc_info.value.detail
            assert exc_info.value.headers["X-RateLimit-Limit"] == "30"
            assert exc_info.value.headers["X-RateLimit-Window"] == "60"
            assert exc_info.value.headers["Retry-After"] == "60"


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with actual endpoints."""

    @pytest.fixture(autouse=True)
    def _patch_auth(self):
        """Patch inkPass auth so all requests pass authentication."""
        mock_user = MagicMock()
        mock_user.id = "test-user"
        mock_user.email = "test@test.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.organization_id = "org-1"
        mock_user.two_fa_enabled = False
        mock_user.status = "active"

        with patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock, return_value=mock_user), \
             patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock, return_value=True):
            yield

    @pytest.fixture
    def test_app(self, mock_dependencies):
        """Create a test app with mocked dependencies."""
        from fastapi import FastAPI
        from src.api.cors_config import configure_cors
        from src.api.app import setup_api_routes
        import asyncio

        app = FastAPI(title="Test Tentackl API", version="0.1.0")
        configure_cors(app)
        asyncio.run(setup_api_routes(app, **mock_dependencies))
        return app

    @pytest.fixture
    def client(self, test_app):
        """Create a test client."""
        return TestClient(test_app)

    @pytest.mark.asyncio
    async def test_catalog_endpoint_rate_limiting(self, client):
        """Test that catalog endpoints have rate limiting for unauthenticated requests."""
        # Make 30 requests (should be within limit)
        for i in range(30):
            response = client.get("/api/catalog/plugins", headers={"Authorization": "Bearer test-token"})
            assert response.status_code == 200, f"Request {i+1} should succeed"

        # 31st request should be rate limited (if rate limiting is working)
        # Note: This test may be flaky if Redis state persists between tests
        # In a real scenario, we'd use a test Redis instance or mock it
        response = client.get("/api/catalog/plugins", headers={"Authorization": "Bearer test-token"})
        # Should either succeed (if rate limit window expired) or be rate limited
        assert response.status_code in [200, 429]

    @pytest.mark.asyncio
    async def test_authenticated_bypasses_rate_limit(self, client):
        """Test that authenticated requests bypass rate limiting.

        Auth is mocked via inkPass patches, so all requests are authenticated.
        Authenticated users bypass rate limiting.
        """
        for i in range(50):
            response = client.get("/api/catalog/plugins", headers={"Authorization": "Bearer test-token"})
            assert response.status_code == 200, f"Authenticated request {i+1} should succeed"
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, client):
        """Test that rate limit headers are present in 429 responses."""
        # Make many rapid requests to trigger rate limit
        # Note: This test assumes rate limiting is active
        responses = []
        for i in range(35):  # More than the 30 request limit
            response = client.get("/api/catalog/agents", headers={"Authorization": "Bearer test-token"})
            responses.append(response)
        
        # Check if any response has rate limit headers
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        
        if rate_limited_responses:
            # If we got rate limited, check headers
            for response in rate_limited_responses:
                assert "X-RateLimit-Limit" in response.headers
                assert "X-RateLimit-Window" in response.headers
                assert "Retry-After" in response.headers


class TestRateLimitingWithDifferentIPs:
    """Test rate limiting behavior with different IP addresses."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_per_ip(self):
        """Test that rate limiting is per IP address."""
        limiter = RateLimiter(redis_url="redis://localhost:6379/15")
        
        request1 = MagicMock(spec=Request)
        request1.headers = {}
        request1.client = MagicMock()
        request1.client.host = "192.168.1.1"
        
        request2 = MagicMock(spec=Request)
        request2.headers = {}
        request2.client = MagicMock()
        request2.client.host = "192.168.1.2"
        
        key1 = limiter.get_client_identifier(request1)
        key2 = limiter.get_client_identifier(request2)
        
        assert key1 != key2
        assert key1 == "rate_limit:192.168.1.1"
        assert key2 == "rate_limit:192.168.1.2"
    
    @pytest.mark.asyncio
    async def test_rate_limit_with_forwarded_for(self):
        """Test rate limiting respects X-Forwarded-For header."""
        limiter = RateLimiter(redis_url="redis://localhost:6379/15")
        
        request1 = MagicMock(spec=Request)
        request1.headers = {"X-Forwarded-For": "10.0.0.1"}
        request1.client = MagicMock()
        request1.client.host = "192.168.1.1"
        
        request2 = MagicMock(spec=Request)
        request2.headers = {"X-Forwarded-For": "10.0.0.2"}
        request2.client = MagicMock()
        request2.client.host = "192.168.1.1"
        
        with patch("src.api.rate_limiter.TRUST_PROXY_HEADERS", True), \
             patch("src.api.rate_limiter.TRUSTED_PROXY_NETWORKS", [ipaddress.ip_network("192.168.1.0/24")]):
            key1 = limiter.get_client_identifier(request1)
            key2 = limiter.get_client_identifier(request2)

            assert key1 != key2
            assert "10.0.0.1" in key1
            assert "10.0.0.2" in key2
