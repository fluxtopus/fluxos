"""Organization routes"""

import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from src.database.database import get_db
from src.services.organization_service import OrganizationService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission
from src.schemas.notification_settings import (
    NotificationSettingsUpdate,
    NotificationSettingsResponse
)

router = APIRouter()

ORG_NAME_PATTERN = re.compile(r"^[\w\s'&.,\-\u00C0-\u024F]+$")


def _validate_org_name(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise ValueError("Organization name must be at least 2 characters")
    if len(value) > 100:
        raise ValueError("Organization name must be at most 100 characters")
    if not ORG_NAME_PATTERN.match(value):
        raise ValueError("Organization name contains invalid characters")
    return value


class OrganizationCreate(BaseModel):
    name: str
    slug: Optional[str] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_org_name(v)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_org_name(v)
        return v


@router.get("")
async def list_organizations(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List user's organizations"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    organizations = OrganizationService.list_user_organizations(
        db,
        auth_context.user.id
    )
    return [{"id": org.id, "name": org.name, "slug": org.slug} for org in organizations]


@router.get("/{organization_id}")
async def get_organization(
    organization_id: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Get organization details"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    organization = OrganizationService.get_organization(db, organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Verify user belongs to organization
    if auth_context.user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "settings": organization.settings,
        "plan_id": organization.plan_id
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Create a new organization"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        organization = OrganizationService.create_organization(
            db,
            request.name,
            request.slug
        )
        return {
            "id": organization.id,
            "name": organization.name,
            "slug": organization.slug
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.patch("/{organization_id}")
async def update_organization(
    organization_id: str,
    request: OrganizationUpdate,
    _perm: None = Depends(require_permission("organization", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update an organization. Requires organization:manage permission."""
    # Verify user belongs to organization
    if auth_context.user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    organization = OrganizationService.update_organization(
        db,
        organization_id,
        request.name,
        request.settings
    )
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "settings": organization.settings
    }


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: str,
    _perm: None = Depends(require_permission("users", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List organization members. Requires users:view permission."""
    # Verify user belongs to organization
    if auth_context.user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    members = OrganizationService.list_members(db, organization_id)
    return members  # Already formatted with id, email, status, role


@router.get("/{organization_id}/notification-settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    organization_id: str,
    _perm: None = Depends(require_permission("organization", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Get organization notification settings. Requires organization:manage permission."""
    # Verify user belongs to organization
    if auth_context.user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    settings = OrganizationService.get_notification_settings(db, organization_id)
    return NotificationSettingsResponse(**settings)


@router.patch("/{organization_id}/notification-settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    organization_id: str,
    request: NotificationSettingsUpdate,
    _perm: None = Depends(require_permission("organization", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update organization notification settings. Requires organization:manage permission."""
    # Verify user belongs to organization
    if auth_context.user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Convert to dict, excluding None values
    update_data = request.model_dump(exclude_none=True)

    organization = OrganizationService.update_notification_settings(
        db, organization_id, update_data
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    settings = OrganizationService.get_notification_settings(db, organization_id)
    return NotificationSettingsResponse(**settings)

