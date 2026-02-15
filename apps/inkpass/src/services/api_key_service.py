"""API Key service"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import hashlib
from src.database.models import APIKey, Organization, User


def generate_api_key() -> str:
    """Generate an API key"""
    return f"inkpass_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    """Hash an API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKeyService:
    """API Key management service"""
    
    @staticmethod
    def create_api_key(
        db: Session,
        organization_id: str,
        name: str,
        user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new API key"""
        # Verify organization exists
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not organization:
            raise ValueError("Organization not found")
        
        # Verify user if provided
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or user.organization_id != organization_id:
                raise ValueError("User not found or doesn't belong to organization")
        
        # Generate API key
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        db_key = APIKey(
            organization_id=organization_id,
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            scopes=scopes or [],
            expires_at=expires_at
        )
        db.add(db_key)
        db.commit()
        db.refresh(db_key)
        
        return {
            "api_key": api_key,
            "id": db_key.id,
            "name": db_key.name,
            "scopes": db_key.scopes,
            "expires_at": db_key.expires_at.isoformat() if db_key.expires_at else None
        }
    
    @staticmethod
    def verify_api_key(db: Session, api_key: str) -> Optional[APIKey]:
        """Verify an API key and return the key record"""
        key_hash = hash_api_key(api_key)
        
        db_key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
        if not db_key:
            return None
        
        # Check expiration
        if db_key.expires_at and db_key.expires_at < datetime.utcnow():
            return None
        
        # Update last used
        db_key.last_used_at = datetime.utcnow()
        db.commit()
        
        return db_key
    
    @staticmethod
    def list_api_keys(
        db: Session,
        organization_id: str,
        user_id: Optional[str] = None
    ) -> List[APIKey]:
        """List API keys for an organization or user"""
        query = db.query(APIKey).filter(APIKey.organization_id == organization_id)
        if user_id:
            query = query.filter(APIKey.user_id == user_id)
        return query.all()
    
    @staticmethod
    def revoke_api_key(db: Session, key_id: str) -> bool:
        """Revoke an API key"""
        db_key = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not db_key:
            return False
        
        db.delete(db_key)
        db.commit()
        return True
    
    @staticmethod
    def update_api_key_scopes(
        db: Session,
        key_id: str,
        scopes: List[str]
    ) -> Optional[APIKey]:
        """Update API key scopes"""
        db_key = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not db_key:
            return None
        
        db_key.scopes = scopes
        db.commit()
        db.refresh(db_key)
        return db_key


