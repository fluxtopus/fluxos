"""Internal routes for service-to-service operations.

These endpoints are called by other services in this stack
and should be protected by API key or internal network policies.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.database.database import get_db
from src.services.permission_template_service import PermissionTemplateService
from src.templates import ProductType
from src.middleware.service_auth import require_service_api_key

router = APIRouter()
require_internal_service_key = require_service_api_key()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class ApplyTemplateRequest(BaseModel):
    organization_id: str
    owner_user_id: str
    product_type: str


class ApplyTemplateResponse(BaseModel):
    success: bool
    template_id: str
    template_name: str
    applied_version: int


# =============================================================================
# INTERNAL ENDPOINTS
# =============================================================================


@router.post("/templates/apply", response_model=ApplyTemplateResponse)
async def apply_template_to_organization(
    request: ApplyTemplateRequest,
    service_name: str = Depends(require_internal_service_key),
    db: Session = Depends(get_db),
):
    """
    Apply a permission template to an organization.

    This internal endpoint can be called during provisioning to:
    1. Apply the appropriate template based on product type
    2. Assign the owner role to the specified user

    The endpoint should be protected by API key or internal network policies.
    """
    # Map product type string to enum
    try:
        product_type_enum = ProductType(request.product_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid product type: {request.product_type}. "
            f"Valid types: {[pt.value for pt in ProductType]}",
        )

    service = PermissionTemplateService(db)

    try:
        org_template = service.apply_template_to_organization(
            organization_id=request.organization_id,
            product_type=product_type_enum,
            owner_user_id=request.owner_user_id,
        )

        return ApplyTemplateResponse(
            success=True,
            template_id=org_template.template_id,
            template_name=org_template.template.name if org_template.template else "",
            applied_version=org_template.applied_version,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply template: {str(e)}",
        )
