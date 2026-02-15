"""Product Plan service for managing subscription tiers and permissions."""

from typing import List, Optional
from sqlalchemy.orm import Session
from src.database.models import ProductPlan, Permission, User
import logging

logger = logging.getLogger(__name__)


class ProductPlanService:
    """Service for managing product plans and automatic permission syncing."""

    def __init__(self, db: Session):
        self.db = db

    async def create_product_plan(
        self,
        organization_id: str,
        name: str,
        slug: str,
        description: Optional[str] = None,
        features: Optional[dict] = None,
        limits: Optional[dict] = None,
        price: Optional[float] = None
    ) -> ProductPlan:
        """Create a new product plan."""
        plan = ProductPlan(
            organization_id=organization_id,
            name=name,
            slug=slug,
            description=description,
            features=features or {},
            limits=limits or {},
            price=price,
            is_active=True
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        logger.info(f"Created product plan: {name} (slug: {slug})")
        return plan

    async def set_plan_permissions(
        self,
        plan_id: str,
        permission_ids: List[str]
    ) -> ProductPlan:
        """Set permissions for a product plan."""
        plan = self.db.query(ProductPlan).get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        permissions = self.db.query(Permission).filter(
            Permission.id.in_(permission_ids)
        ).all()

        plan.permissions = permissions
        self.db.commit()
        self.db.refresh(plan)

        logger.info(f"Set {len(permissions)} permissions for plan {plan.name}")
        return plan

    async def assign_user_to_plan(
        self,
        user_id: str,
        plan_id: str,
        preserve_custom_permissions: bool = True
    ) -> User:
        """
        Assign user to a product plan and sync permissions automatically.

        Args:
            user_id: User ID to assign
            plan_id: Product plan ID
            preserve_custom_permissions: Keep user-specific permissions (default: True)

        Returns:
            Updated user object
        """
        user = self.db.query(User).get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        new_plan = self.db.query(ProductPlan).get(plan_id)
        if not new_plan:
            raise ValueError(f"Plan {plan_id} not found")

        old_plan = user.product_plan

        # Get permission sets
        old_plan_perm_ids = (
            set(p.id for p in old_plan.permissions) if old_plan else set()
        )
        new_plan_perm_ids = set(p.id for p in new_plan.permissions)
        current_user_perm_ids = set(p.id for p in user.user_permissions)

        if preserve_custom_permissions:
            # Calculate custom permissions (not from old plan)
            custom_perm_ids = current_user_perm_ids - old_plan_perm_ids

            # Final permissions = new plan + custom
            final_perm_ids = new_plan_perm_ids | custom_perm_ids
        else:
            # Replace all with plan permissions
            final_perm_ids = new_plan_perm_ids

        # Update user permissions
        user.user_permissions = self.db.query(Permission).filter(
            Permission.id.in_(final_perm_ids)
        ).all()

        # Update user's plan
        user.product_plan_id = plan_id

        self.db.commit()
        self.db.refresh(user)

        logger.info(
            f"Assigned user {user.email} to plan {new_plan.name}. "
            f"Permissions: {len(user.user_permissions)}"
        )

        return user

    async def remove_user_from_plan(
        self,
        user_id: str,
        remove_all_permissions: bool = False
    ) -> User:
        """
        Remove user from their current plan.

        Args:
            user_id: User ID
            remove_all_permissions: If True, removes ALL permissions.
                                   If False, keeps custom permissions.
        """
        user = self.db.query(User).get(user_id)
        if not user or not user.product_plan_id:
            return user

        old_plan = user.product_plan
        old_plan_perm_ids = set(p.id for p in old_plan.permissions)
        current_user_perm_ids = set(p.id for p in user.user_permissions)

        if remove_all_permissions:
            user.user_permissions = []
        else:
            # Keep only custom permissions
            custom_perm_ids = current_user_perm_ids - old_plan_perm_ids
            user.user_permissions = self.db.query(Permission).filter(
                Permission.id.in_(custom_perm_ids)
            ).all()

        user.product_plan_id = None
        self.db.commit()
        self.db.refresh(user)

        logger.info(f"Removed user {user.email} from plan {old_plan.name}")
        return user

    async def get_plan_users(self, plan_id: str) -> List[User]:
        """Get all users assigned to a plan."""
        return self.db.query(User).filter_by(product_plan_id=plan_id).all()

    async def get_organization_plans(
        self,
        organization_id: str,
        active_only: bool = True
    ) -> List[ProductPlan]:
        """Get all product plans for an organization."""
        query = self.db.query(ProductPlan).filter_by(
            organization_id=organization_id
        )
        if active_only:
            query = query.filter_by(is_active=True)
        return query.all()
