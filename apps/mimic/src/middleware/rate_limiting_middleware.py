"""Rate limiting middleware for FastAPI"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from src.middleware.rate_limiting import check_rate_limit
import structlog

logger = structlog.get_logger()


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting API requests"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract user ID from request (set by auth middleware)
        user_id = request.state.user_id if hasattr(request.state, 'user_id') else None
        
        if user_id:
            # Check rate limit
            if not check_rate_limit(user_id, "user", max_requests=100, window_seconds=60):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
        
        response = await call_next(request)
        return response

