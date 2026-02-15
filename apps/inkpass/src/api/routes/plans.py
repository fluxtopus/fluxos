"""Product plan routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from src.database.database import get_db
from src.database.models import ProductPlan
from src.services.plan_service import PlanService
from src.services.product_plan_service import ProductPlanService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission

router = APIRouter()


class PlanCreate(BaseModel):
    name: str
    slug: str
    features: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None
    price: Optional[float] = None


class ProductPlanCreate(BaseModel):
    """Create a product plan with organization context"""
    name: str
    slug: str
    description: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None
    price: Optional[float] = None


class SetPlanPermissions(BaseModel):
    """Set permissions for a product plan"""
    permission_ids: List[str]


class AssignUserToPlan(BaseModel):
    """Assign user to a product plan"""
    product_plan_id: str
    preserve_custom_permissions: bool = True


@router.get("")
async def list_plans(db: Session = Depends(get_db)):
    """List all available plans"""
    plans = PlanService.list_plans(db)
    return [{
        "id": plan.id,
        "name": plan.name,
        "slug": plan.slug,
        "features": plan.features,
        "limits": plan.limits,
        "price": float(plan.price) if plan.price else None
    } for plan in plans]


@router.get("/{plan_id}")
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """Get plan details"""
    plan = PlanService.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    return {
        "id": plan.id,
        "name": plan.name,
        "slug": plan.slug,
        "features": plan.features,
        "limits": plan.limits,
        "price": float(plan.price) if plan.price else None
    }


@router.post("/{plan_id}/subscribe")
async def subscribe_to_plan(
    plan_id: str,
    _perm: None = Depends(require_permission("organization", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Subscribe organization to a plan. Requires organization:manage permission."""

    try:
        subscription = PlanService.subscribe_organization(
            db,
            auth_context.user.organization_id,
            plan_id
        )
        return {
            "message": "Subscribed successfully",
            "plan_id": subscription.plan_id,
            "starts_at": subscription.starts_at.isoformat()
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Product Plan endpoints with permission syncing

@router.post("/product-plans", status_code=status.HTTP_201_CREATED)
async def create_product_plan(
    plan_data: ProductPlanCreate,
    _perm: None = Depends(require_permission("plans", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Create a product plan for the authenticated user's organization.
    Requires plans:create permission.

    Product plans define subscription tiers with automatic permission management.
    """

    service = ProductPlanService(db)
    plan = await service.create_product_plan(
        organization_id=auth_context.user.organization_id,
        name=plan_data.name,
        slug=plan_data.slug,
        description=plan_data.description,
        features=plan_data.features,
        limits=plan_data.limits,
        price=plan_data.price
    )

    return plan.to_dict()


@router.get("/product-plans")
async def list_product_plans(
    _perm: None = Depends(require_permission("plans", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    active_only: bool = True
):
    """
    List all product plans. Requires plans:view permission.
    """

    service = ProductPlanService(db)
    plans = await service.get_organization_plans(
        organization_id=auth_context.user.organization_id,
        active_only=active_only
    )

    return [plan.to_dict() for plan in plans]


@router.get("/product-plans/{plan_id}")
async def get_product_plan(
    plan_id: str,
    _perm: None = Depends(require_permission("plans", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Get product plan details with permissions. Requires plans:view permission.
    """

    plan = db.query(ProductPlan).get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product plan not found"
        )

    # Verify plan belongs to user's organization
    if plan.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return plan.to_dict_with_permissions()


@router.post("/product-plans/{plan_id}/permissions")
async def set_product_plan_permissions(
    plan_id: str,
    permissions_data: SetPlanPermissions,
    _perm: None = Depends(require_permission("plans", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Set permissions for a product plan. Requires plans:manage permission.

    This defines which permissions users will automatically receive when assigned to this plan.
    """

    # Verify plan exists and belongs to user's organization
    plan = db.query(ProductPlan).get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product plan not found"
        )

    if plan.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    service = ProductPlanService(db)
    try:
        updated_plan = await service.set_plan_permissions(
            plan_id=plan_id,
            permission_ids=permissions_data.permission_ids
        )
        return updated_plan.to_dict_with_permissions()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/users/{user_id}/product-plan")
async def assign_user_to_product_plan(
    user_id: str,
    assignment_data: AssignUserToPlan,
    _perm: None = Depends(require_permission("users", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Assign a user to a product plan. Requires users:manage permission.

    This will automatically:
    1. Remove permissions from their old plan
    2. Add permissions from the new plan
    3. Preserve custom user-specific permissions (if preserve_custom_permissions=True)
    """

    # Verify user exists and belongs to same organization
    from src.database.models import User
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Verify plan exists and belongs to same organization
    plan = db.query(ProductPlan).get(assignment_data.product_plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product plan not found"
        )

    if plan.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product plan does not belong to your organization"
        )

    service = ProductPlanService(db)
    try:
        updated_user = await service.assign_user_to_plan(
            user_id=user_id,
            plan_id=assignment_data.product_plan_id,
            preserve_custom_permissions=assignment_data.preserve_custom_permissions
        )

        return {
            "user_id": updated_user.id,
            "email": updated_user.email,
            "product_plan_id": updated_user.product_plan_id,
            "product_plan_name": plan.name,
            "permission_count": len(updated_user.user_permissions),
            "message": "User assigned to product plan successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/product-plans/{plan_id}/users")
async def get_product_plan_users(
    plan_id: str,
    _perm: None = Depends(require_permission("plans", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Get all users assigned to a product plan. Requires plans:view permission.
    """

    # Verify plan exists and belongs to user's organization
    plan = db.query(ProductPlan).get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product plan not found"
        )

    if plan.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    service = ProductPlanService(db)
    users = await service.get_plan_users(plan_id)

    return {
        "plan_id": plan_id,
        "plan_name": plan.name,
        "user_count": len(users),
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "permission_count": len(user.user_permissions)
            }
            for user in users
        ]
    }


