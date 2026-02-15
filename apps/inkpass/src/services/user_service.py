"""User service"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import User, Organization
from src.security.password import hash_password


class UserService:
    """User management service"""
    
    @staticmethod
    def create_user(
        db: Session,
        email: str,
        password: str,
        organization_id: str
    ) -> User:
        """Create a new user"""
        # Check if user exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("User with this email already exists")
        
        # Verify organization exists
        organization = db.query(Organization).filter(Organization.id == organization_id).first()
        if not organization:
            raise ValueError("Organization not found")
        
        user = User(
            email=email,
            password_hash=hash_password(password),
            organization_id=organization_id
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    @staticmethod
    def get_user(db: Session, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        return db.query(User).filter(User.id == user_id).first()
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Get a user by email"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def list_organization_users(db: Session, organization_id: str) -> List[User]:
        """List all users in an organization"""
        return db.query(User).filter(User.organization_id == organization_id).all()
    
    @staticmethod
    def update_user(
        db: Session,
        user_id: str,
        email: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[User]:
        """Update a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        if email:
            # Check if email is already taken
            existing = db.query(User).filter(
                User.email == email,
                User.id != user_id
            ).first()
            if existing:
                raise ValueError("Email already in use")
            user.email = email
        
        if status:
            user.status = status
        
        db.commit()
        db.refresh(user)
        return user
    
    @staticmethod
    def delete_user(db: Session, user_id: str) -> bool:
        """Soft delete a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.status = "deleted"
        db.commit()
        return True


