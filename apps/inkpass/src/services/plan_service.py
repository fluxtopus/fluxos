"""Product plan service"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
from src.database.models import ProductPlan, OrganizationPlan, Organization


class PlanService:
    """Product plan management service"""
    
    @staticmethod
    def create_plan(
        db: Session,
        name: str,
        slug: str,
        features: Optional[Dict[str, Any]] = None,
        limits: Optional[Dict[str, Any]] = None,
        price: Optional[float] = None
    ) -> ProductPlan:
        """Create a new product plan"""
        # Check if slug exists
        existing = db.query(ProductPlan).filter(ProductPlan.slug == slug).first()
        if existing:
            raise ValueError("Plan with this slug already exists")
        
        plan = ProductPlan(
            name=name,
            slug=slug,
            features=features or {},
            limits=limits or {},
            price=price
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan
    
    @staticmethod
    def get_plan(db: Session, plan_id: str) -> Optional[ProductPlan]:
        """Get a plan by ID"""
        return db.query(ProductPlan).filter(ProductPlan.id == plan_id).first()
    
    @staticmethod
    def get_plan_by_slug(db: Session, slug: str) -> Optional[ProductPlan]:
        """Get a plan by slug"""
        return db.query(ProductPlan).filter(ProductPlan.slug == slug).first()
    
    @staticmethod
    def list_plans(db: Session) -> List[ProductPlan]:
        """List all available plans"""
        return db.query(ProductPlan).all()
    
    @staticmethod
    def subscribe_organization(
        db: Session,
        organization_id: str,
        plan_id: str
    ) -> OrganizationPlan:
        """Subscribe an organization to a plan"""
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        plan = db.query(ProductPlan).filter(ProductPlan.id == plan_id).first()
        
        if not organization or not plan:
            raise ValueError("Organization or plan not found")
        
        # End current active subscription if exists
        db.query(OrganizationPlan).filter(
            OrganizationPlan.organization_id == organization_id,
            OrganizationPlan.status == "active"
        ).update({"status": "ended", "ends_at": datetime.utcnow()})
        
        # Create new subscription
        subscription = OrganizationPlan(
            organization_id=organization_id,
            plan_id=plan_id,
            starts_at=datetime.utcnow(),
            status="active"
        )
        db.add(subscription)
        
        # Update organization plan_id
        organization.plan_id = plan_id
        
        db.commit()
        db.refresh(subscription)
        return subscription
    
    @staticmethod
    def get_organization_plan(
        db: Session,
        organization_id: str
    ) -> Optional[ProductPlan]:
        """Get the current active plan for an organization"""
        subscription = db.query(OrganizationPlan).filter(
            OrganizationPlan.organization_id == organization_id,
            OrganizationPlan.status == "active"
        ).order_by(OrganizationPlan.starts_at.desc()).first()
        
        if not subscription:
            return None
        
        return db.query(ProductPlan).filter(
            ProductPlan.id == subscription.plan_id
        ).first()


