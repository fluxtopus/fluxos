"""Permission routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from src.database.database import get_db
from src.services.permission_service import PermissionService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission

router = APIRouter()


class PermissionCheck(BaseModel):
    """Request to check if current user has a permission."""
    resource: str
    action: str


class PermissionCheckResponse(BaseModel):
    """Response indicating if permission is allowed."""
    allowed: bool
    resource: str
    action: str


class PermissionCreate(BaseModel):
    resource: str
    action: str
    conditions: Optional[Dict[str, Any]] = None


class PermissionUpdate(BaseModel):
    resource: Optional[str] = None
    action: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None


class PermissionAssign(BaseModel):
    group_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheck,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Check if the current user has a specific permission.

    Used by downstream services (Mimic, Tentackl) to validate permissions.
    Returns {allowed: true/false, resource, action}.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    allowed = PermissionService.check_permission(
        db,
        auth_context.user.id,
        request.resource,
        request.action
    )

    return PermissionCheckResponse(
        allowed=allowed,
        resource=request.resource,
        action=request.action
    )


@router.get("")
async def list_permissions(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List permissions in organization"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    permissions = PermissionService.list_organization_permissions(
        db,
        auth_context.user.organization_id
    )
    return [{
        "id": perm.id,
        "resource": perm.resource,
        "action": perm.action,
        "conditions": perm.conditions
    } for perm in permissions]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_permission(
    request: PermissionCreate,
    _perm: None = Depends(require_permission("permissions", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Create a new permission. Requires permissions:create permission."""
    
    try:
        permission = PermissionService.create_permission(
            db,
            auth_context.user.organization_id,
            request.resource,
            request.action,
            request.conditions
        )
        return {
            "id": permission.id,
            "resource": permission.resource,
            "action": permission.action,
            "conditions": permission.conditions
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{permission_id}")
async def update_permission(
    permission_id: str,
    request: PermissionUpdate,
    _perm: None = Depends(require_permission("permissions", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update a permission. Requires permissions:manage permission."""
    
    permission = PermissionService.update_permission(
        db,
        permission_id,
        request.resource,
        request.action,
        request.conditions
    )
    
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    
    # Verify permission belongs to same organization
    if permission.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "id": permission.id,
        "resource": permission.resource,
        "action": permission.action,
        "conditions": permission.conditions
    }


@router.delete("/{permission_id}")
async def delete_permission(
    permission_id: str,
    _perm: None = Depends(require_permission("permissions", "delete")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Delete a permission. Requires permissions:delete permission."""
    
    # Verify permission belongs to same organization
    permission = PermissionService.get_permission(db, permission_id)
    if not permission or permission.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    success = PermissionService.delete_permission(db, permission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    
    return {"message": "Permission deleted successfully"}


@router.post("/{permission_id}/assign")
async def assign_permission(
    permission_id: str,
    request: PermissionAssign,
    _perm: None = Depends(require_permission("permissions", "assign")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Assign a permission to a group or user. Requires permissions:assign permission."""
    
    # Verify permission belongs to same organization
    permission = PermissionService.get_permission(db, permission_id)
    if not permission or permission.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        if request.group_id:
            success = PermissionService.assign_permission_to_group(
                db,
                permission_id,
                request.group_id
            )
        elif request.user_id:
            success = PermissionService.assign_permission_to_user(
                db,
                permission_id,
                request.user_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either group_id or user_id must be provided"
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group or user not found"
            )
        
        return {"message": "Permission assigned successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


