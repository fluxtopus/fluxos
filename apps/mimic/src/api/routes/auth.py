"""Authentication routes"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from src.database.database import get_db
from src.database.models import User, APIKey
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel
from src.config import settings
import secrets
import hashlib

router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class APIKeyCreate(BaseModel):
    name: str


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key: str
    created_at: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def hash_api_key(key: str) -> str:
    """Hash an API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from API key"""
    api_key = credentials.credentials
    
    # Hash the provided key
    key_hash = hash_api_key(api_key)
    
    # Find the API key in database
    db_key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
    if not db_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Get the user
    user = db.query(User).filter(User.id == db_key.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


@router.post("/register")
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {"id": user.id, "email": user.email}


@router.post("/login")
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """Login and get API key"""
    # Find user
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Generate API key
    api_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(api_key)
    
    # Store API key
    db_key = APIKey(
        user_id=user.id,
        key_hash=key_hash,
        name="Default"
    )
    db.add(db_key)
    db.commit()
    
    return {"api_key": api_key, "user_id": user.id}


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new API key"""
    # Generate API key
    api_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(api_key)
    
    # Store API key
    db_key = APIKey(
        user_id=current_user.id,
        key_hash=key_hash,
        name=key_data.name
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    
    return APIKeyResponse(
        id=db_key.id,
        name=db_key.name,
        key=api_key,  # Only returned once
        created_at=db_key.created_at.isoformat()
    )


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "subscription_tier": current_user.subscription_tier,
        "subscription_expires_at": current_user.subscription_expires_at.isoformat() if current_user.subscription_expires_at else None
    }

