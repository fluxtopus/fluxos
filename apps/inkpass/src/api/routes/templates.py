"""Template routes for permission template management."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from src.database.database import get_db
from src.database.models import PermissionTemplate, RoleTemplate, OrganizationTemplate
from src.services.permission_template_service import PermissionTemplateService
from src.services.role_service import RoleService
from src.middleware.auth_middleware import (
    get_auth_context,
    AuthContext,
    require_permission,
    require_owner_role,
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


class TemplateResponse(BaseModel):
    id: str
    name: str
    product_type: str
    version: int
    description: Optional[str]
    is_active: bool
    role_count: int


class TemplateDetailResponse(TemplateResponse):
    roles: List[RoleResponse]


class PermissionResponse(BaseModel):
    resource: str
    action: str


class OrganizationTemplateResponse(BaseModel):
    id: str
    organization_id: str
    template_id: str
    template_name: str
    applied_version: int
    current_version: int
    needs_update: bool
    applied_at: str


# =============================================================================
# TEMPLATE ENDPOINTS
# =============================================================================


@router.get("", response_model=List[TemplateResponse])
async def list_templates(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    List all available permission templates.

    Templates define permission sets for different product types.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    templates = db.query(PermissionTemplate).filter(
        PermissionTemplate.is_active == True
    ).all()

    return [
        TemplateResponse(
            id=t.id,
            name=t.name,
            product_type=t.product_type,
            version=t.version,
            description=t.description,
            is_active=t.is_active,
            role_count=len(t.roles) if t.roles else 0,
        )
        for t in templates
    ]


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get a specific template with its roles.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    template = db.query(PermissionTemplate).filter(
        PermissionTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return TemplateDetailResponse(
        id=template.id,
        name=template.name,
        product_type=template.product_type,
        version=template.version,
        description=template.description,
        is_active=template.is_active,
        role_count=len(template.roles) if template.roles else 0,
        roles=[
            RoleResponse(
                id=r.id,
                role_name=r.role_name,
                display_name=r.display_name,
                description=r.description,
                inherits_from=r.inherits_from,
                priority=r.priority,
            )
            for r in sorted(template.roles, key=lambda x: -x.priority)
        ],
    )


@router.get("/{template_id}/roles", response_model=List[RoleResponse])
async def get_template_roles(
    template_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get roles for a specific template.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    template = db.query(PermissionTemplate).filter(
        PermissionTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return [
        RoleResponse(
            id=r.id,
            role_name=r.role_name,
            display_name=r.display_name,
            description=r.description,
            inherits_from=r.inherits_from,
            priority=r.priority,
        )
        for r in sorted(template.roles, key=lambda x: -x.priority)
    ]


@router.get(
    "/{template_id}/roles/{role_name}/permissions",
    response_model=List[PermissionResponse],
)
async def get_role_permissions(
    template_id: str,
    role_name: str,
    include_inherited: bool = True,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get permissions for a specific role in a template.

    Args:
        include_inherited: If True, include permissions inherited from parent roles
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    role = db.query(RoleTemplate).filter(
        RoleTemplate.template_id == template_id,
        RoleTemplate.role_name == role_name,
    ).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found in template",
        )

    role_service = RoleService(db)
    permissions = role_service.get_role_permissions(
        role.id,
        include_inherited=include_inherited,
    )

    return [
        PermissionResponse(resource=p["resource"], action=p["action"])
        for p in permissions
    ]


# =============================================================================
# ORGANIZATION TEMPLATE ENDPOINTS
# =============================================================================


@router.get("/organization/current", response_model=Optional[OrganizationTemplateResponse])
async def get_organization_template(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get the template applied to the current organization.
    """
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    service = PermissionTemplateService(db)
    org_template = service.get_organization_template(
        auth_context.user.organization_id
    )

    if not org_template:
        return None

    return OrganizationTemplateResponse(
        id=org_template.id,
        organization_id=org_template.organization_id,
        template_id=org_template.template_id,
        template_name=org_template.template.name if org_template.template else "",
        applied_version=org_template.applied_version,
        current_version=org_template.template.version if org_template.template else 0,
        needs_update=(
            org_template.template.version > org_template.applied_version
            if org_template.template
            else False
        ),
        applied_at=org_template.applied_at.isoformat() if org_template.applied_at else "",
    )


@router.post("/organization/sync")
async def sync_organization_template(
    _owner: None = Depends(require_owner_role()),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Sync the organization to the latest template version.

    Requires owner role.
    """
    service = PermissionTemplateService(db)
    org_template = service.get_organization_template(
        auth_context.user.organization_id
    )

    if not org_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No template applied to this organization",
        )

    if org_template.applied_version >= org_template.template.version:
        return {
            "message": "Organization is already at latest version",
            "version": org_template.applied_version,
        }

    # Update to latest version
    org_template.applied_version = org_template.template.version
    db.commit()

    return {
        "message": "Organization synced to latest template version",
        "version": org_template.applied_version,
    }
