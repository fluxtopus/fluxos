"""Permission service with ABAC evaluation"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import Permission, User, Group, Organization


class PermissionService:
    """Permission management and evaluation service"""
    
    @staticmethod
    def create_permission(
        db: Session,
        organization_id: str,
        resource: str,
        action: str,
        conditions: Optional[Dict[str, Any]] = None
    ) -> Permission:
        """Create a new permission"""
        # Verify organization exists
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not organization:
            raise ValueError("Organization not found")
        
        permission = Permission(
            organization_id=organization_id,
            resource=resource,
            action=action,
            conditions=conditions or {}
        )
        db.add(permission)
        db.commit()
        db.refresh(permission)
        return permission
    
    @staticmethod
    def get_permission(db: Session, permission_id: str) -> Optional[Permission]:
        """Get a permission by ID"""
        return db.query(Permission).filter(Permission.id == permission_id).first()
    
    @staticmethod
    def list_organization_permissions(
        db: Session,
        organization_id: str
    ) -> List[Permission]:
        """List all permissions in an organization"""
        return db.query(Permission).filter(
            Permission.organization_id == organization_id
        ).all()
    
    @staticmethod
    def update_permission(
        db: Session,
        permission_id: str,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> Optional[Permission]:
        """Update a permission"""
        permission = db.query(Permission).filter(
            Permission.id == permission_id
        ).first()
        if not permission:
            return None
        
        if resource:
            permission.resource = resource
        if action:
            permission.action = action
        if conditions is not None:
            permission.conditions = conditions
        
        db.commit()
        db.refresh(permission)
        return permission
    
    @staticmethod
    def delete_permission(db: Session, permission_id: str) -> bool:
        """Delete a permission"""
        permission = db.query(Permission).filter(
            Permission.id == permission_id
        ).first()
        if not permission:
            return False
        
        db.delete(permission)
        db.commit()
        return True
    
    @staticmethod
    def assign_permission_to_group(
        db: Session,
        permission_id: str,
        group_id: str
    ) -> bool:
        """Assign a permission to a group"""
        permission = db.query(Permission).filter(
            Permission.id == permission_id
        ).first()
        group = db.query(Group).filter(Group.id == group_id).first()
        
        if not permission or not group:
            return False
        
        if permission.organization_id != group.organization_id:
            raise ValueError("Permission and group must belong to same organization")
        
        if permission not in group.permissions:
            group.permissions.append(permission)
            db.commit()
        
        return True
    
    @staticmethod
    def assign_permission_to_user(
        db: Session,
        permission_id: str,
        user_id: str
    ) -> bool:
        """Assign a permission directly to a user"""
        permission = db.query(Permission).filter(
            Permission.id == permission_id
        ).first()
        user = db.query(User).filter(User.id == user_id).first()
        
        if not permission or not user:
            return False
        
        if permission.organization_id != user.organization_id:
            raise ValueError("Permission and user must belong to same organization")
        
        if permission not in user.user_permissions:
            user.user_permissions.append(permission)
            db.commit()
        
        return True
    
    @staticmethod
    def check_permission(
        db: Session,
        user_id: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a user has a specific permission (ABAC evaluation)"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        # Get all permissions for user (direct + from groups)
        all_permissions = set()
        
        # Direct user permissions
        for perm in user.user_permissions:
            all_permissions.add(perm)
        
        # Permissions from groups
        for group in user.groups:
            for perm in group.permissions:
                all_permissions.add(perm)
        
        # Check if any permission matches
        for perm in all_permissions:
            if perm.resource == resource and perm.action == action:
                # Evaluate conditions if present
                if perm.conditions:
                    if not PermissionService._evaluate_conditions(
                        perm.conditions,
                        context or {}
                    ):
                        continue
                return True
        
        return False
    
    @staticmethod
    def _evaluate_conditions(
        conditions: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate ABAC conditions"""
        # Simple condition evaluation
        # In production, you'd want a more sophisticated evaluation engine
        for key, value in conditions.items():
            if key not in context:
                return False
            if context[key] != value:
                return False
        return True


