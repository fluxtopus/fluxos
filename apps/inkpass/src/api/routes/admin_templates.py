"""Admin template routes for template sync and propagation.

These endpoints are admin-only operations for managing permission templates.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from src.database.database import get_db
from src.services.admin_template_sync_service import AdminTemplateSyncService
from src.middleware.auth_middleware import (
    get_auth_context,
    AuthContext,
    require_permission,
)

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class SyncResultResponse(BaseModel):
    created: List[str]
    updated: List[str]
    unchanged: List[str]
    errors: List[str]


class PropagateResultResponse(BaseModel):
    template_name: str
    orgs_updated: int
    permissions_added: int
    errors: List[str]


class TemplateStatusResponse(BaseModel):
    name: str
    product_type: str
    code_version: int
    db_version: Optional[int]
    exists_in_db: bool
    needs_update: bool


class SyncStatusResponse(BaseModel):
    templates: List[TemplateStatusResponse]
    needs_sync: bool


class MigrationDetailResponse(BaseModel):
    organization_id: str
    organization_name: str
    product_type: str
    owner_user_id: Optional[str]
    action: str
    error: Optional[str] = None


class MigrationResultResponse(BaseModel):
    orgs_migrated: int
    dry_run: bool
    details: List[MigrationDetailResponse]
    errors: List[str]


# =============================================================================
# ADMIN TEMPLATE SYNC ENDPOINTS
# =============================================================================


@router.post("/sync", response_model=SyncResultResponse)
async def sync_templates(
    _perm: None = Depends(require_permission("permissions", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Sync all templates from code definitions to database.

    This compares the TEMPLATE_REGISTRY in code with the database and:
    - Creates templates that don't exist in DB
    - Updates templates that have a newer version in code
    - Leaves unchanged templates alone

    Requires permissions:manage permission.
    """
    service = AdminTemplateSyncService(db)
    result = service.sync_templates_from_code()

    return SyncResultResponse(
        created=result.created,
        updated=result.updated,
        unchanged=result.unchanged,
        errors=result.errors,
    )


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    _perm: None = Depends(require_permission("permissions", "read")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Get the sync status comparing code vs DB templates.

    Shows version differences between code TEMPLATE_REGISTRY and database.

    Requires permissions:read permission.
    """
    service = AdminTemplateSyncService(db)
    status = service.get_sync_status()

    return SyncStatusResponse(
        templates=[
            TemplateStatusResponse(
                name=t["name"],
                product_type=t["product_type"],
                code_version=t["code_version"],
                db_version=t["db_version"],
                exists_in_db=t["exists_in_db"],
                needs_update=t["needs_update"],
            )
            for t in status.templates
        ],
        needs_sync=status.needs_sync,
    )


@router.post("/{template_id}/propagate", response_model=PropagateResultResponse)
async def propagate_template(
    template_id: str,
    _perm: None = Depends(require_permission("permissions", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Propagate template changes to all organizations using it.

    This updates the applied_version in organization_templates
    to match the current template version.

    Requires permissions:manage permission.
    """
    service = AdminTemplateSyncService(db)
    result = service.propagate_template(template_id)

    if result.errors and not result.template_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.errors[0],
        )

    return PropagateResultResponse(
        template_name=result.template_name,
        orgs_updated=result.orgs_updated,
        permissions_added=result.permissions_added,
        errors=result.errors,
    )


@router.post("/migrate-orgs", response_model=MigrationResultResponse)
async def migrate_existing_orgs(
    dry_run: bool = Query(True, description="If True, don't make changes, just report what would happen"),
    _perm: None = Depends(require_permission("permissions", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Migrate existing organizations to the template system.

    This will:
    1. Detect which template each org should have (by settings/product type)
    2. Apply templates to orgs that don't have one
    3. Assign owner roles to existing owners

    Use dry_run=true (default) to preview changes without applying them.

    Requires permissions:manage permission.
    """
    service = AdminTemplateSyncService(db)
    result = service.migrate_existing_orgs(dry_run=dry_run)

    return MigrationResultResponse(
        orgs_migrated=result.orgs_migrated,
        dry_run=result.dry_run,
        details=[
            MigrationDetailResponse(
                organization_id=d["organization_id"],
                organization_name=d["organization_name"],
                product_type=d["product_type"],
                owner_user_id=d.get("owner_user_id"),
                action=d["action"],
                error=d.get("error"),
            )
            for d in result.details
        ],
        errors=result.errors,
    )
