"""Role routes for role management within organizations."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from src.database.database import get_db
from src.services.role_service import RoleService
from src.middleware.auth_middleware import (
    get_auth_context,
    AuthContext,
    require_permission,
)

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class RoleResponse(BaseModel):
    id: str
    role_name: str
    display_name: str
    description: Optional[str]
    inherits_from: Optional[str]
    priority: int


class PermissionResponse(BaseModel):
    resource: str
    action: str


class UserRoleResponse(BaseModel):
    user_id: str
    organization_id: str
    role: Optional[RoleResponse]


class AssignRoleRequest(BaseModel):
    role: str


# =============================================================================
# ROLE ENDPOINTS
# =============================================================================


@router.get("", response_model=List[RoleResponse])
async def list_available_roles(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    List roles available for the current organization.

    Returns roles from the template applied to the organization.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    role_service = RoleService(db)
    roles = role_service.get_available_roles(auth_context.user.organization_id)

    return [
        RoleResponse(
            id=r.id,
            role_name=r.role_name,
            display_name=r.display_name,
            description=r.description,
            inherits_from=r.inherits_from,
            priority=r.priority,
        )
        for r in roles
    ]


@router.get("/users/me/permissions", response_model=List[PermissionResponse])
async def get_my_permissions(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get the current user's effective permissions.

    Returns all permissions resolved from the user's role template,
    including inherited permissions.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    role_service = RoleService(db)
    permissions = role_service.get_user_permissions(
        auth_context.user.id,
        auth_context.user.organization_id,
    )

    return [
        PermissionResponse(resource=p["resource"], action=p["action"])
        for p in permissions
    ]


@router.get("/users/me", response_model=UserRoleResponse)
async def get_my_role(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get the current user's role in the organization.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    role_service = RoleService(db)
    role = role_service.get_user_role(
        auth_context.user.id,
        auth_context.user.organization_id,
    )

    return UserRoleResponse(
        user_id=auth_context.user.id,
        organization_id=auth_context.user.organization_id,
        role=RoleResponse(
            id=role.id,
            role_name=role.role_name,
            display_name=role.display_name,
            description=role.description,
            inherits_from=role.inherits_from,
            priority=role.priority,
        ) if role else None,
    )


@router.get("/users/{user_id}/permissions", response_model=List[PermissionResponse])
async def get_user_permissions(
    user_id: str,
    _perm: None = Depends(require_permission("users", "read")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get a user's effective permissions.

    Requires users:read permission.
    """
    role_service = RoleService(db)
    permissions = role_service.get_user_permissions(
        user_id,
        auth_context.user.organization_id,
    )

    return [
        PermissionResponse(resource=p["resource"], action=p["action"])
        for p in permissions
    ]


@router.get("/users/{user_id}", response_model=UserRoleResponse)
async def get_user_role(
    user_id: str,
    _perm: None = Depends(require_permission("users", "read")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get a user's role in the organization.

    Requires users:read permission.
    """
    role_service = RoleService(db)
    role = role_service.get_user_role(
        user_id,
        auth_context.user.organization_id,
    )

    return UserRoleResponse(
        user_id=user_id,
        organization_id=auth_context.user.organization_id,
        role=RoleResponse(
            id=role.id,
            role_name=role.role_name,
            display_name=role.display_name,
            description=role.description,
            inherits_from=role.inherits_from,
            priority=role.priority,
        ) if role else None,
    )


@router.put("/users/{user_id}", response_model=UserRoleResponse)
async def assign_role_to_user(
    user_id: str,
    request: AssignRoleRequest,
    _perm: None = Depends(require_permission("users", "update")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Assign a role to a user in the organization.

    Requires users:update permission.
    """
    role_service = RoleService(db)

    try:
        user_org = role_service.assign_role_to_user(
            user_id,
            auth_context.user.organization_id,
            request.role,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Get the updated role
    role = role_service.get_user_role(
        user_id,
        auth_context.user.organization_id,
    )

    return UserRoleResponse(
        user_id=user_id,
        organization_id=auth_context.user.organization_id,
        role=RoleResponse(
            id=role.id,
            role_name=role.role_name,
            display_name=role.display_name,
            description=role.description,
            inherits_from=role.inherits_from,
            priority=role.priority,
        ) if role else None,
    )
