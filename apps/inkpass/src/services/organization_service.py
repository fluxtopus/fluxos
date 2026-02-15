"""Organization service"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import Organization, User, UserOrganization


class OrganizationService:
    """Organization management service"""
    
    @staticmethod
    def create_organization(
        db: Session,
        name: str,
        slug: Optional[str] = None
    ) -> Organization:
        """Create a new organization"""
        if not slug:
            slug = name.lower().replace(" ", "-")
        
        # Check if slug exists
        existing = db.query(Organization).filter(Organization.slug == slug).first()
        if existing:
            raise ValueError("Organization with this slug already exists")
        
        organization = Organization(
            name=name,
            slug=slug
        )
        db.add(organization)
        db.commit()
        db.refresh(organization)
        return organization
    
    @staticmethod
    def get_organization(db: Session, organization_id: str) -> Optional[Organization]:
        """Get an organization by ID"""
        return db.query(Organization).filter(Organization.id == organization_id).first()
    
    @staticmethod
    def get_organization_by_slug(db: Session, slug: str) -> Optional[Organization]:
        """Get an organization by slug"""
        return db.query(Organization).filter(Organization.slug == slug).first()
    
    @staticmethod
    def list_user_organizations(db: Session, user_id: str) -> List[Organization]:
        """List all organizations a user belongs to"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return []
        
        return [user.organization] if user.organization else []
    
    @staticmethod
    def update_organization(
        db: Session,
        organization_id: str,
        name: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Optional[Organization]:
        """Update an organization"""
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            return None
        
        if name:
            organization.name = name
        if settings is not None:
            organization.settings = settings
        
        db.commit()
        db.refresh(organization)
        return organization
    
    @staticmethod
    def list_members(db: Session, organization_id: str) -> List[Dict[str, Any]]:
        """List all members of an organization with their roles"""
        # Get users with their UserOrganization records for role info
        users = db.query(User).filter(User.organization_id == organization_id).all()

        result = []
        for user in users:
            # Look up role from UserOrganization
            user_org = db.query(UserOrganization).filter(
                UserOrganization.user_id == user.id,
                UserOrganization.organization_id == organization_id
            ).first()

            result.append({
                "id": user.id,
                "email": user.email,
                "status": user.status,
                "role": user_org.role if user_org else "member"
            })

        return result

    @staticmethod
    def update_notification_settings(
        db: Session,
        organization_id: str,
        notification_settings: Dict[str, Any]
    ) -> Optional[Organization]:
        """
        Update organization notification settings.

        Merges new settings with existing ones (partial update).

        Args:
            db: Database session
            organization_id: Organization ID
            notification_settings: Dict of notification settings to update

        Returns:
            Updated organization or None if not found
        """
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()

        if not organization:
            return None

        # Get existing settings or empty dict
        current_settings = organization.settings or {}
        current_notification = current_settings.get("notification", {})

        # Merge new notification settings (only non-None values)
        updated_notification = {
            **current_notification,
            **{k: v for k, v in notification_settings.items() if v is not None}
        }

        # Update full settings
        organization.settings = {
            **current_settings,
            "notification": updated_notification
        }

        db.commit()
        db.refresh(organization)
        return organization

    @staticmethod
    def get_notification_settings(db: Session, organization_id: str) -> Dict[str, Any]:
        """
        Get organization notification settings with defaults applied.

        Args:
            db: Database session
            organization_id: Organization ID

        Returns:
            Notification settings dict with defaults
        """
        from src.services.notification_service import NotificationService

        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()

        return NotificationService.get_notification_settings(organization)

