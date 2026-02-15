"""Auth middleware to set user_id in request state"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src.database.database import SessionLocal
from src.database.models import User, APIKey
import structlog

logger = structlog.get_logger()


def hash_api_key(key: str) -> str:
    """Hash an API key for storage"""
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and set user_id in request state for rate limiting"""
    
    async def dispatch(self, request: Request, call_next):
        # Try to extract user from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                # Extract API key and get user
                api_key = auth_header.replace("Bearer ", "")
                key_hash = hash_api_key(api_key)
                
                db = SessionLocal()
                try:
                    db_key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
                    if db_key:
                        user = db.query(User).filter(User.id == db_key.user_id).first()
                        if user:
                            request.state.user_id = user.id
                finally:
                    db.close()
            except Exception:
                # If auth fails, user_id won't be set (rate limiting will be per-IP)
                pass
        
        response = await call_next(request)
        return response

