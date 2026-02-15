"""Group service"""

from typing import Optional, List
from sqlalchemy.orm import Session
from src.database.models import Group, User, Organization


class GroupService:
    """Group management service"""
    
    @staticmethod
    def create_group(
        db: Session,
        organization_id: str,
        name: str,
        description: Optional[str] = None
    ) -> Group:
        """Create a new group"""
        # Verify organization exists
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not organization:
            raise ValueError("Organization not found")
        
        # Check if group name already exists in organization
        existing = db.query(Group).filter(
            Group.organization_id == organization_id,
            Group.name == name
        ).first()
        if existing:
            raise ValueError("Group with this name already exists in organization")
        
        group = Group(
            organization_id=organization_id,
            name=name,
            description=description
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        return group
    
    @staticmethod
    def get_group(db: Session, group_id: str) -> Optional[Group]:
        """Get a group by ID"""
        return db.query(Group).filter(Group.id == group_id).first()
    
    @staticmethod
    def list_organization_groups(db: Session, organization_id: str) -> List[Group]:
        """List all groups in an organization"""
        return db.query(Group).filter(Group.organization_id == organization_id).all()
    
    @staticmethod
    def update_group(
        db: Session,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Group]:
        """Update a group"""
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            return None
        
        if name:
            # Check if name conflicts
            existing = db.query(Group).filter(
                Group.organization_id == group.organization_id,
                Group.name == name,
                Group.id != group_id
            ).first()
            if existing:
                raise ValueError("Group with this name already exists")
            group.name = name
        
        if description is not None:
            group.description = description
        
        db.commit()
        db.refresh(group)
        return group
    
    @staticmethod
    def delete_group(db: Session, group_id: str) -> bool:
        """Delete a group"""
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            return False
        
        db.delete(group)
        db.commit()
        return True
    
    @staticmethod
    def add_user_to_group(db: Session, group_id: str, user_id: str) -> bool:
        """Add a user to a group"""
        group = db.query(Group).filter(Group.id == group_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        
        if not group or not user:
            return False
        
        # Check if user belongs to same organization
        if user.organization_id != group.organization_id:
            raise ValueError("User and group must belong to same organization")
        
        # Check if already in group
        if user in group.users:
            return True
        
        group.users.append(user)
        db.commit()
        return True
    
    @staticmethod
    def remove_user_from_group(db: Session, group_id: str, user_id: str) -> bool:
        """Remove a user from a group"""
        group = db.query(Group).filter(Group.id == group_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        
        if not group or not user:
            return False
        
        if user not in group.users:
            return False
        
        group.users.remove(user)
        db.commit()
        return True


