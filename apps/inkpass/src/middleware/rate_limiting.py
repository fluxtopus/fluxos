"""Rate limiting middleware"""

from typing import Optional
from fastapi import Request, HTTPException, status
import redis
from src.config import settings
import structlog

logger = structlog.get_logger()

# Initialize Redis client
redis_client: Optional[redis.Redis] = None


def _build_rate_limit_subject(request: Request, identifier: Optional[str] = None) -> str:
    """Build stable subject key for throttling."""
    client_ip = request.client.host if request.client else "unknown"
    if identifier:
        normalized = identifier.strip().lower()
        if normalized:
            return f"{client_ip}:{normalized}"
    return client_ip


async def enforce_rate_limit(
    request: Request,
    key: str,
    limit: int,
    window: int = 60,
    identifier: Optional[str] = None,
) -> None:
    """Apply a rate limit check for a request."""
    if not redis_client:
        # If Redis is not available, skip rate limiting
        return

    subject = _build_rate_limit_subject(request, identifier=identifier)
    redis_key = f"rate_limit:{key}:{subject}"
    current = redis_client.incr(redis_key)

    if current == 1:
        redis_client.expire(redis_key, window)

    if current > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per {window} seconds",
        )


def init_redis():
    """Initialize Redis client"""
    global redis_client
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        logger.info("Redis connected for rate limiting")
    except Exception as e:
        logger.warning("Redis not available for rate limiting", error=str(e))
        redis_client = None


def rate_limit(key: str, limit: int, window: int = 60):
    """Rate limiting decorator"""
    async def rate_limiter(request: Request):
        await enforce_rate_limit(request=request, key=key, limit=limit, window=window)
    
    return rate_limiter

