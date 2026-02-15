"""User routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List
from src.database.database import get_db
from src.services.user_service import UserService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    status: Optional[str] = None


@router.get("")
async def list_users(
    _perm: None = Depends(require_permission("users", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List users in organization. Requires users:view permission."""
    
    users = UserService.list_organization_users(
        db,
        auth_context.user.organization_id
    )
    return [{
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "status": user.status
    } for user in users]


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    _perm: None = Depends(require_permission("users", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Get user details. Requires users:view permission."""
    
    user = UserService.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify user belongs to same organization
    if user.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "status": user.status,
        "two_fa_enabled": user.two_fa_enabled
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    _perm: None = Depends(require_permission("users", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Create a new user in organization. Requires users:create permission."""
    
    try:
        user = UserService.create_user(
            db,
            request.email,
            request.password,
            auth_context.user.organization_id
        )
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "status": user.status
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    request: UserUpdate,
    _perm: None = Depends(require_permission("users", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update a user. Requires users:manage permission."""
    
    # Verify user belongs to same organization
    target_user = UserService.get_user(db, user_id)
    if not target_user or target_user.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        user = UserService.update_user(
            db,
            user_id,
            request.email,
            request.status
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "status": user.status
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    _perm: None = Depends(require_permission("users", "delete")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Delete a user (soft delete). Requires users:delete permission."""

    # Verify user belongs to same organization
    target_user = UserService.get_user(db, user_id)
    if not target_user or target_user.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    success = UserService.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {"message": "User deleted successfully"}


@router.get("/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    _perm: None = Depends(require_permission("users", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Get all permissions for a user. Requires users:view permission."""

    from src.database.models import User
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify user belongs to same organization
    if user.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return {
        "user_id": user.id,
        "email": user.email,
        "permissions": [
            {
                "id": p.id,
                "resource": p.resource,
                "action": p.action,
                "conditions": p.conditions or {}
            }
            for p in user.user_permissions
        ]
    }


