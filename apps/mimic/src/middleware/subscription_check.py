"""Subscription check middleware"""

from fastapi import HTTPException, status
from datetime import datetime
from src.database.models import User

def check_subscription(user: User, feature: str = "byok") -> bool:
    """Check if user has active subscription for a feature"""
    if feature == "byok":
        # BYOK requires annual subscription
        if user.subscription_tier != "annual":
            return False
        
        if user.subscription_expires_at:
            return user.subscription_expires_at > datetime.utcnow()
        
        return False
    
    return True


def require_subscription(feature: str = "byok"):
    """Decorator to require active subscription"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs or args
            current_user = kwargs.get("current_user")
            if not current_user:
                # Try to find in args (usually first dependency)
                for arg in args:
                    if isinstance(arg, User):
                        current_user = arg
                        break
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            if not check_subscription(current_user, feature):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"{feature} requires an active annual subscription"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

