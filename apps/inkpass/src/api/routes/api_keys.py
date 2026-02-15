"""API Key routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from src.database.database import get_db
from src.services.api_key_service import APIKeyService
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission

router = APIRouter()


class APIKeyCreate(BaseModel):
    name: str
    user_id: Optional[str] = None
    scopes: Optional[List[str]] = None
    expires_in_days: Optional[int] = None


class APIKeyUpdate(BaseModel):
    scopes: List[str]


@router.get("")
async def list_api_keys(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """List API keys"""
    if not auth_context.user and not auth_context.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    organization_id = auth_context.organization_id
    user_id = auth_context.user.id if auth_context.user else None
    
    api_keys = APIKeyService.list_api_keys(db, organization_id, user_id)
    return [{
        "id": key.id,
        "name": key.name,
        "scopes": key.scopes,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None
    } for key in api_keys]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: APIKeyCreate,
    _perm: None = Depends(require_permission("api_keys", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Create a new API key. Requires api_keys:create permission."""
    
    try:
        result = APIKeyService.create_api_key(
            db,
            auth_context.user.organization_id,
            request.name,
            request.user_id or auth_context.user.id,
            request.scopes,
            request.expires_in_days
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    _perm: None = Depends(require_permission("api_keys", "delete")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Revoke an API key. Requires api_keys:delete permission."""
    
    # Verify key belongs to same organization
    from src.database.models import APIKey
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key or key.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    success = APIKeyService.revoke_api_key(db, key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return {"message": "API key revoked successfully"}


@router.patch("/{key_id}")
async def update_api_key(
    key_id: str,
    request: APIKeyUpdate,
    _perm: None = Depends(require_permission("api_keys", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Update API key scopes. Requires api_keys:manage permission."""
    
    # Verify key belongs to same organization
    from src.database.models import APIKey
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key or key.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    key = APIKeyService.update_api_key_scopes(db, key_id, request.scopes)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return {
        "id": key.id,
        "name": key.name,
        "scopes": key.scopes
    }


@router.get("/{key_id}/usage")
async def get_api_key_usage(
    key_id: str,
    _perm: None = Depends(require_permission("api_keys", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """Get API key usage stats. Requires api_keys:view permission."""
    
    # Verify key belongs to same organization
    from src.database.models import APIKey
    key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not key or key.organization_id != auth_context.user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "id": key.id,
        "name": key.name,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "created_at": key.created_at.isoformat()
    }


