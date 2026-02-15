# REVIEW:
# - Middleware runs before dependencies, so request.state.auth_user is never set; authenticated requests are effectively IP-limited.
# - Config is split between env vars and settings (REDIS_URL/TRUST_PROXY_HEADERS); inconsistent config source.
# - Both middleware and per-route dependencies enforce rate limits; possible duplication or conflicting limits.
"""Rate limiting utility for API endpoints."""

import os
import time
import threading
import uuid
import ipaddress
from typing import Optional, Set
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import redis.asyncio as redis_async
import structlog
from datetime import datetime

logger = structlog.get_logger()


class InMemoryRateLimiter:
    """
    In-memory rate limiter fallback for when Redis is unavailable.

    Uses a simple sliding window counter per key with periodic cleanup
    of expired entries. Applies a restrictiveness multiplier so that
    in-memory limits are stricter than Redis-based limits (default: 50%
    of the configured max_requests).

    Thread-safe via a threading.Lock.
    """

    # Fraction of max_requests allowed when using in-memory fallback.
    # 0.5 means only half the normal limit is allowed during Redis outages.
    RESTRICTIVENESS_MULTIPLIER = 0.5

    # How often to run cleanup of expired entries (in seconds).
    CLEANUP_INTERVAL_SECONDS = 60

    def __init__(self):
        # key -> list of request timestamps (float)
        self._counters: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Check if a request is within the in-memory rate limit.

        The effective limit is max_requests * RESTRICTIVENESS_MULTIPLIER
        (rounded down, minimum 1).

        Returns True if within limit, False if exceeded.
        """
        now = time.monotonic()
        effective_max = max(1, int(max_requests * self.RESTRICTIVENESS_MULTIPLIER))

        with self._lock:
            # Periodic cleanup of expired keys
            if now - self._last_cleanup > self.CLEANUP_INTERVAL_SECONDS:
                self._cleanup(now)
                self._last_cleanup = now

            # Get or create the timestamps list for this key
            timestamps = self._counters.get(key)
            if timestamps is None:
                timestamps = []
                self._counters[key] = timestamps

            # Remove expired entries for this key
            cutoff = now - window_seconds
            # Filter in-place: keep only entries within the window
            timestamps[:] = [ts for ts in timestamps if ts > cutoff]

            # Check limit
            if len(timestamps) >= effective_max:
                return False

            # Record this request
            timestamps.append(now)
            return True

    def _cleanup(self, now: float) -> None:
        """Remove keys that have no entries within any reasonable window.

        Called periodically under lock. Removes keys whose newest entry
        is older than 5 minutes (covers any practical window_seconds value).
        """
        stale_keys = []
        max_window = 300  # 5 minutes — generous upper bound
        cutoff = now - max_window
        for key, timestamps in self._counters.items():
            if not timestamps or timestamps[-1] <= cutoff:
                stale_keys.append(key)
        for key in stale_keys:
            del self._counters[key]

        if stale_keys:
            logger.debug(
                "In-memory rate limiter cleanup",
                removed_keys=len(stale_keys),
                remaining_keys=len(self._counters),
            )

    def reset(self) -> None:
        """Clear all counters. Useful for testing."""
        with self._lock:
            self._counters.clear()
            self._last_cleanup = time.monotonic()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
# Whether to trust X-Forwarded-For headers (disable in non-proxy environments)
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
TRUSTED_PROXY_CIDRS = [
    cidr.strip()
    for cidr in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",")
    if cidr.strip()
]
TRUSTED_PROXY_NETWORKS = []
for cidr in TRUSTED_PROXY_CIDRS:
    try:
        TRUSTED_PROXY_NETWORKS.append(ipaddress.ip_network(cidr, strict=False))
    except ValueError:
        logger.warning("Invalid trusted proxy CIDR", cidr=cidr)

if TRUST_PROXY_HEADERS and not TRUSTED_PROXY_NETWORKS:
    logger.warning(
        "TRUST_PROXY_HEADERS enabled but TRUSTED_PROXY_CIDRS is empty; "
        "falling back to direct client IP"
    )


def _is_request_from_trusted_proxy(direct_ip: str) -> bool:
    if not TRUSTED_PROXY_NETWORKS:
        return False
    try:
        proxy_ip = ipaddress.ip_address(direct_ip)
    except ValueError:
        return False
    return any(proxy_ip in network for network in TRUSTED_PROXY_NETWORKS)


def _extract_client_ip(request: Request) -> str:
    """
    Extract client IP with validation.

    Only trusts X-Forwarded-For if TRUST_PROXY_HEADERS is enabled
    and the IP is a valid format.
    """
    direct_ip = request.client.host if request.client else "unknown"

    if not TRUST_PROXY_HEADERS:
        return direct_ip

    if not _is_request_from_trusted_proxy(direct_ip):
        return direct_ip

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client from trusted proxy chain)
        first_ip = forwarded_for.split(",")[0].strip()
        # Validate IP format to prevent spoofing with garbage data
        try:
            ipaddress.ip_address(first_ip)
            return first_ip
        except ValueError:
            logger.warning("Invalid X-Forwarded-For IP", ip=first_ip[:50])
            return direct_ip

    return direct_ip


class RateLimiter:
    """Rate limiter using Redis sliding window algorithm with connection pooling.

    Falls back to an in-memory counter when Redis is unavailable.
    The in-memory fallback is more restrictive (50% of configured limits)
    to prevent abuse during Redis outages.
    """

    # Class-level connection pool (shared across all instances)
    _pool: Optional[redis_async.ConnectionPool] = None

    # Shared in-memory fallback (class-level so all RateLimiter instances share it)
    _memory_fallback: InMemoryRateLimiter = InMemoryRateLimiter()

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url

    @classmethod
    async def get_pool(cls, redis_url: str = REDIS_URL) -> redis_async.ConnectionPool:
        """Get or create the shared connection pool."""
        if cls._pool is None:
            cls._pool = redis_async.ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                decode_responses=True
            )
            logger.info("Rate limiter connection pool created", max_connections=20)
        return cls._pool

    async def _get_redis(self) -> redis_async.Redis:
        """Get Redis client from the connection pool."""
        pool = await self.get_pool(self.redis_url)
        return redis_async.Redis(connection_pool=pool)
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """
        Check if request is within rate limit using sliding window.
        
        Args:
            key: Unique identifier for the rate limit (e.g., IP address, user ID)
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            True if within limit, False if exceeded
        """
        redis_client = await self._get_redis()
        try:
            current_time = int(datetime.utcnow().timestamp())
            window_start = current_time - window_seconds
            
            # Use Redis sorted set for sliding window
            pipe = redis_client.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current entries in window
            pipe.zcard(key)
            
            # Add current request with unique ID to avoid overwrites within same second
            request_id = f"{current_time}:{uuid.uuid4().hex[:8]}"
            pipe.zadd(key, {request_id: current_time})
            
            # Set expiry (window + 60 seconds buffer)
            pipe.expire(key, window_seconds + 60)
            
            results = await pipe.execute()
            # Results: [zremrangebyscore_count, zcard_count, zadd_count, expire_result]
            current_count = results[1] if len(results) > 1 else 0
            
            # Check if within limit
            return current_count < max_requests
            
        except Exception as e:
            logger.warning(
                "Redis rate limit check failed, using in-memory fallback",
                error=str(e),
                key=key,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            # Fail closed via in-memory fallback (more restrictive than Redis limits)
            return self._memory_fallback.check_rate_limit(
                key=key,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
        # Note: No aclose() needed - connection pool manages connections
    
    def get_client_identifier(self, request: Request) -> str:
        """
        Get unique identifier for rate limiting.

        Uses validated IP from X-Forwarded-For or direct client IP.
        """
        client_ip = _extract_client_ip(request)
        return f"rate_limit:{client_ip}"


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit_unauthenticated(
    max_requests: int = 30,
    window_seconds: int = 60
):
    """
    Dependency to rate limit unauthenticated requests.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            request: Request,
            user: Optional[AuthUser] = Depends(optional_auth()),
            _: None = Depends(rate_limit_unauthenticated())
        ):
            # Rate limiting is applied if user is None
    """
    async def rate_limit_dependency(request: Request) -> None:
        # Check if user is authenticated (from request state set by optional_auth)
        auth_user = getattr(request.state, "auth_user", None)

        # Only rate limit unauthenticated requests
        if auth_user is None:
            client_id = rate_limiter.get_client_identifier(request)
            key = f"rate_limit:unauthenticated:{client_id}"

            within_limit = await rate_limiter.check_rate_limit(
                key=key,
                max_requests=max_requests,
                window_seconds=window_seconds
            )

            if not within_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds} seconds. Please authenticate or wait before retrying.",
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Window": str(window_seconds),
                        "Retry-After": str(window_seconds)
                    }
                )

        return None

    return rate_limit_dependency


def rate_limit_webhook(
    max_requests: int = 10,
    window_seconds: int = 60
):
    """
    Dependency to rate limit webhook requests by source_id.

    Usage:
        @router.post("/webhook/{source_id}")
        async def webhook(
            source_id: str,
            _: None = Depends(rate_limit_webhook(max_requests=10, window_seconds=60))
        ):
            ...
    """
    async def rate_limit_dependency(request: Request) -> None:
        # Extract source_id from path parameters
        source_id = request.path_params.get("source_id", "unknown")
        key = f"rate_limit:webhook:{source_id}"

        within_limit = await rate_limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds
        )

        if not within_limit:
            logger.warning(
                "Webhook rate limit exceeded",
                source_id=source_id,
                max_requests=max_requests,
                window_seconds=window_seconds
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds} seconds for this webhook source.",
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Window": str(window_seconds),
                    "Retry-After": str(window_seconds)
                }
            )

        return None

    return rate_limit_dependency


def rate_limit_playground(
    max_requests: int = 10,
    window_seconds: int = 60
):
    """
    Dependency to rate limit playground endpoints by client IP.

    Playground endpoints are always unauthenticated, so rate limiting
    is always applied based on the client's IP address.

    Usage:
        @router.post("/plan")
        async def plan_workflow(
            request: Request,
            _rate_limit: None = Depends(rate_limit_playground(max_requests=10, window_seconds=60))
        ):
            ...
    """
    async def rate_limit_dependency(request: Request) -> None:
        client_ip = _extract_client_ip(request)
        key = f"rate_limit:playground:{client_ip}"

        within_limit = await rate_limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds
        )

        if not within_limit:
            logger.warning(
                "Playground rate limit exceeded",
                client_ip=client_ip,
                max_requests=max_requests,
                window_seconds=window_seconds,
                path=str(request.url.path)
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds} seconds. Please wait before retrying.",
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Window": str(window_seconds),
                    "Retry-After": str(window_seconds)
                }
            )

        return None

    return rate_limit_dependency


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply rate limiting to all API endpoints.

    Applies configurable rate limits per client, with support for:
    - Authenticated users (rate limited by user ID)
    - Unauthenticated users (rate limited by IP)
    - Path-specific rate limits (stricter for expensive endpoints)
    - Excluded paths (health checks, metrics)
    """

    def __init__(
        self,
        app,
        default_max_requests: int = 100,
        default_window_seconds: int = 60,
        exclude_paths: Optional[Set[str]] = None,
        strict_paths: Optional[dict] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            default_max_requests: Default max requests per window (100)
            default_window_seconds: Default time window in seconds (60)
            exclude_paths: Set of paths to exclude from rate limiting (e.g., {"/health"})
            strict_paths: Dict of path prefixes to stricter limits
                         (e.g., {"/api/evaluations": (20, 60)})
        """
        super().__init__(app)
        self.default_max_requests = default_max_requests
        self.default_window_seconds = default_window_seconds
        self.exclude_paths = exclude_paths or {"/health", "/metrics", "/docs", "/openapi.json"}
        self.strict_paths = strict_paths or {}
        self.rate_limiter = RateLimiter()

    def _get_rate_limit_config(self, path: str) -> tuple[int, int]:
        """Get rate limit config for a path."""
        # Check strict paths first (path prefix match)
        for prefix, (max_req, window) in self.strict_paths.items():
            if path.startswith(prefix):
                return max_req, window
        return self.default_max_requests, self.default_window_seconds

    def _get_client_key(self, request: Request) -> str:
        """Get rate limit key for the client."""
        # Check for authenticated user
        auth_user = getattr(request.state, "auth_user", None)
        if auth_user:
            return f"rate_limit:user:{auth_user.id}"

        # Fall back to IP-based rate limiting with validation
        client_ip = _extract_client_ip(request)
        return f"rate_limit:ip:{client_ip}"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Apply rate limiting to incoming requests."""
        path = request.url.path

        # Skip rate limiting for excluded paths
        if path in self.exclude_paths:
            return await call_next(request)

        # Get rate limit config for this path
        max_requests, window_seconds = self._get_rate_limit_config(path)
        client_key = self._get_client_key(request)

        # Check rate limit
        within_limit = await self.rate_limiter.check_rate_limit(
            key=client_key,
            max_requests=max_requests,
            window_seconds=window_seconds
        )

        if not within_limit:
            logger.warning(
                "Rate limit exceeded",
                path=path,
                client_key=client_key,
                max_requests=max_requests,
                window_seconds=window_seconds
            )
            return Response(
                content=f'{{"detail": "Rate limit exceeded: {max_requests} requests per {window_seconds} seconds"}}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Window": str(window_seconds),
                    "Retry-After": str(window_seconds)
                }
            )

        # Process request and add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Window"] = str(window_seconds)

        return response
