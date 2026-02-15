"""Provider keys routes (BYOK)"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional
from src.database.database import get_db
from src.database.models import User, ProviderKey
from src.api.auth import require_permission, AuthContext
from src.services.key_encryption import KeyEncryptionService
from src.services.provider_validator import ProviderValidatorService
from src.middleware.subscription_check import check_subscription, require_subscription
import uuid

router = APIRouter()
encryption_service = KeyEncryptionService()
validator_service = ProviderValidatorService()


class ProviderKeyCreate(BaseModel):
    provider_type: str  # email, sms, slack, discord, telegram, webhook
    api_key: Optional[str] = None
    secret: Optional[str] = None
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    from_email: Optional[str] = None
    from_number: Optional[str] = None


class ProviderKeyResponse(BaseModel):
    id: str
    provider_type: str
    is_active: bool
    created_at: str
    updated_at: str


class ProviderKeyTestResponse(BaseModel):
    success: bool
    message: str


@router.post("/provider-keys", response_model=ProviderKeyResponse)
async def create_provider_key(
    key_data: ProviderKeyCreate,
    auth: Annotated[AuthContext, Depends(require_permission("provider_keys", "create"))],
    db: Session = Depends(get_db)
):
    """Create a provider key (BYOK) - requires annual subscription"""
    # Get user for subscription check (business logic)
    current_user = db.query(User).filter(User.id == auth.user_id).first()
    # Check subscription for BYOK feature
    if current_user and not check_subscription(current_user, "byok"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="BYOK requires an active annual subscription. Upgrade at /api/v1/billing/subscribe"
        )
    # Check if key already exists for this provider type
    existing_key = db.query(ProviderKey).filter(
        ProviderKey.user_id == auth.user_id,
        ProviderKey.provider_type == key_data.provider_type
    ).first()
    
    if existing_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider key for {key_data.provider_type} already exists. Use PUT to update."
        )
    
    # Encrypt sensitive data
    encrypted_api_key = None
    encrypted_secret = None
    encrypted_bot_token = None
    
    if key_data.api_key:
        encrypted_api_key = encryption_service.encrypt(key_data.api_key)
    if key_data.secret:
        encrypted_secret = encryption_service.encrypt(key_data.secret)
    if key_data.bot_token:
        encrypted_bot_token = encryption_service.encrypt(key_data.bot_token)
    
    # Create provider key
    provider_key = ProviderKey(
        id=str(uuid.uuid4()),
        user_id=auth.user_id,
        provider_type=key_data.provider_type,
        encrypted_api_key=encrypted_api_key,
        encrypted_secret=encrypted_secret,
        webhook_url=key_data.webhook_url,
        bot_token=encrypted_bot_token,
        from_email=key_data.from_email,
        from_number=key_data.from_number,
        is_active=True
    )
    
    db.add(provider_key)
    db.commit()
    db.refresh(provider_key)
    
    return ProviderKeyResponse(
        id=provider_key.id,
        provider_type=provider_key.provider_type,
        is_active=provider_key.is_active,
        created_at=provider_key.created_at.isoformat(),
        updated_at=provider_key.updated_at.isoformat()
    )


@router.get("/provider-keys", response_model=list[ProviderKeyResponse])
async def list_provider_keys(
    auth: Annotated[AuthContext, Depends(require_permission("provider_keys", "view"))],
    db: Session = Depends(get_db)
):
    """List all provider keys for current user"""
    provider_keys = db.query(ProviderKey).filter(
        ProviderKey.user_id == auth.user_id
    ).all()
    
    return [
        ProviderKeyResponse(
            id=pk.id,
            provider_type=pk.provider_type,
            is_active=pk.is_active,
            created_at=pk.created_at.isoformat(),
            updated_at=pk.updated_at.isoformat()
        )
        for pk in provider_keys
    ]


@router.put("/provider-keys/{provider_type}", response_model=ProviderKeyResponse)
async def update_provider_key(
    provider_type: str,
    key_data: ProviderKeyCreate,
    auth: Annotated[AuthContext, Depends(require_permission("provider_keys", "update"))],
    db: Session = Depends(get_db)
):
    """Update a provider key"""
    provider_key = db.query(ProviderKey).filter(
        ProviderKey.user_id == auth.user_id,
        ProviderKey.provider_type == provider_type
    ).first()
    
    if not provider_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider key for {provider_type} not found"
        )
    
    # Update fields
    if key_data.api_key:
        provider_key.encrypted_api_key = encryption_service.encrypt(key_data.api_key)
    if key_data.secret:
        provider_key.encrypted_secret = encryption_service.encrypt(key_data.secret)
    if key_data.webhook_url:
        provider_key.webhook_url = key_data.webhook_url
    if key_data.bot_token:
        provider_key.bot_token = encryption_service.encrypt(key_data.bot_token)
    if key_data.from_email:
        provider_key.from_email = key_data.from_email
    if key_data.from_number:
        provider_key.from_number = key_data.from_number
    
    db.commit()
    db.refresh(provider_key)
    
    return ProviderKeyResponse(
        id=provider_key.id,
        provider_type=provider_key.provider_type,
        is_active=provider_key.is_active,
        created_at=provider_key.created_at.isoformat(),
        updated_at=provider_key.updated_at.isoformat()
    )


@router.delete("/provider-keys/{provider_type}")
async def delete_provider_key(
    provider_type: str,
    auth: Annotated[AuthContext, Depends(require_permission("provider_keys", "delete"))],
    db: Session = Depends(get_db)
):
    """Delete a provider key"""
    provider_key = db.query(ProviderKey).filter(
        ProviderKey.user_id == auth.user_id,
        ProviderKey.provider_type == provider_type
    ).first()
    
    if not provider_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider key for {provider_type} not found"
        )
    
    db.delete(provider_key)
    db.commit()
    
    return {"message": f"Provider key for {provider_type} deleted successfully"}


@router.post("/provider-keys/{provider_type}/test", response_model=ProviderKeyTestResponse)
async def test_provider_key(
    provider_type: str,
    auth: Annotated[AuthContext, Depends(require_permission("provider_keys", "test"))],
    db: Session = Depends(get_db)
):
    """Test a provider key connection"""
    provider_key = db.query(ProviderKey).filter(
        ProviderKey.user_id == auth.user_id,
        ProviderKey.provider_type == provider_type
    ).first()
    
    if not provider_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider key for {provider_type} not found"
        )
    
    # Decrypt credentials
    api_key = None
    secret = None
    webhook_url = None
    bot_token = None
    
    if provider_key.encrypted_api_key:
        api_key = encryption_service.decrypt(provider_key.encrypted_api_key)
    if provider_key.encrypted_secret:
        secret = encryption_service.decrypt(provider_key.encrypted_secret)
    if provider_key.webhook_url:
        webhook_url = provider_key.webhook_url
    if provider_key.bot_token:
        bot_token = encryption_service.decrypt(provider_key.bot_token)
    
    # Test connection
    try:
        success = await validator_service.validate_provider(
            provider_type=provider_type,
            api_key=api_key,
            secret=secret,
            webhook_url=webhook_url,
            bot_token=bot_token
        )
        
        if success:
            return ProviderKeyTestResponse(
                success=True,
                message=f"Connection to {provider_type} successful"
            )
        else:
            return ProviderKeyTestResponse(
                success=False,
                message=f"Connection to {provider_type} failed"
            )
    except Exception as e:
        return ProviderKeyTestResponse(
            success=False,
            message=f"Error testing connection: {str(e)}"
        )

