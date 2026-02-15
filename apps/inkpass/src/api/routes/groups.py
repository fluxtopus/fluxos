"""Group routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from src.database.database import get_db
from src.services.group_service import GroupService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission

router = APIRouter()


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.get("")
async def list_groups(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List groups in organization"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    groups = GroupService.list_organization_groups(
        db,
        auth_context.user.organization_id
    )
    return [{
        "id": group.id,
        "name": group.name,
        "description": group.description
    } for group in groups]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_group(
    request: GroupCreate,
    _perm: None = Depends(require_permission("groups", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Create a new group. Requires groups:create permission."""
    
    try:
        group = GroupService.create_group(
            db,
            auth_context.user.organization_id,
            request.name,
            request.description
        )
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{group_id}")
async def update_group(
    group_id: str,
    request: GroupUpdate,
    _perm: None = Depends(require_permission("groups", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update a group. Requires groups:manage permission."""
    
    # Verify group belongs to same organization
    group = GroupService.get_group(db, group_id)
    if not group or group.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        group = GroupService.update_group(
            db,
            group_id,
            request.name,
            request.description
        )
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found"
            )
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    _perm: None = Depends(require_permission("groups", "delete")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Delete a group. Requires groups:delete permission."""
    
    # Verify group belongs to same organization
    group = GroupService.get_group(db, group_id)
    if not group or group.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    success = GroupService.delete_group(db, group_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    return {"message": "Group deleted successfully"}


@router.post("/{group_id}/members/{user_id}")
async def add_user_to_group(
    group_id: str,
    user_id: str,
    _perm: None = Depends(require_permission("groups", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Add a user to a group. Requires groups:manage permission."""
    
    try:
        success = GroupService.add_user_to_group(db, group_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group or user not found"
            )
        return {"message": "User added to group successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{group_id}/members/{user_id}")
async def remove_user_from_group(
    group_id: str,
    user_id: str,
    _perm: None = Depends(require_permission("groups", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Remove a user from a group. Requires groups:manage permission."""
    
    success = GroupService.remove_user_from_group(db, group_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group, user, or membership not found"
        )
    
    return {"message": "User removed from group successfully"}


