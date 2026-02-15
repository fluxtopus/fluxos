"""Permission checking middleware"""

from typing import Callable, List
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from src.database.database import get_db
from src.services.permission_service import PermissionService
from src.middleware.auth_middleware import get_auth_context, AuthContext


def require_permission(resource: str, action: str):
    """Decorator to require a specific permission"""
    async def permission_checker(request: Request):
        auth_context = await get_auth_context(request)
        
        if not auth_context.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        db: Session = next(get_db())
        has_permission = PermissionService.check_permission(
            db,
            auth_context.user.id,
            resource,
            action
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}"
            )
        
        return auth_context
    
    return permission_checker


def require_any_permission(permissions: List[tuple[str, str]]):
    """Require any of the specified permissions"""
    async def permission_checker(request: Request):
        auth_context = await get_auth_context(request)
        
        if not auth_context.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        db: Session = next(get_db())
        for resource, action in permissions:
            if PermissionService.check_permission(
                db,
                auth_context.user.id,
                resource,
                action
            ):
                return auth_context
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    
    return permission_checker


