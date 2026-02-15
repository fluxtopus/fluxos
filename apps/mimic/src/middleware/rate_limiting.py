"""Rate limiting middleware"""

from fastapi import Request, HTTPException, status
from typing import Dict
from datetime import datetime, timedelta
from collections import defaultdict
import time

# Simple in-memory rate limiter (use Redis in production)
_rate_limits: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))


def check_rate_limit(
    user_id: str,
    limit_type: str = "user",
    max_requests: int = 100,
    window_seconds: int = 60
) -> bool:
    """Check if user has exceeded rate limit"""
    now = time.time()
    key = f"{user_id}:{limit_type}"
    
    # Clean old entries
    _rate_limits[user_id][limit_type] = [
        timestamp for timestamp in _rate_limits[user_id][limit_type]
        if now - timestamp < window_seconds
    ]
    
    # Check limit
    if len(_rate_limits[user_id][limit_type]) >= max_requests:
        return False
    
    # Add current request
    _rate_limits[user_id][limit_type].append(now)
    return True


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware"""
    # Extract user ID from request (from API key or auth token)
    user_id = request.headers.get("X-User-ID")
    
    if user_id:
        # Per-user rate limit
        if not check_rate_limit(user_id, "user", max_requests=100, window_seconds=60):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
    
    response = await call_next(request)
    return response

