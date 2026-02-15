"""Two-Factor Authentication service"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import User
from src.security.two_fa import (
    generate_2fa_secret,
    get_2fa_uri,
    generate_qr_code,
    verify_2fa_code,
    generate_backup_codes
)
from src.security.encryption import encrypt_data, decrypt_data


class TwoFAService:
    """2FA service"""
    
    @staticmethod
    def setup_2fa(db: Session, user_id: str) -> Dict[str, Any]:
        """Setup 2FA for a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        
        secret = generate_2fa_secret()
        uri = get_2fa_uri(secret, user.email)
        qr_code = generate_qr_code(uri)
        
        # Store encrypted secret temporarily (user needs to verify before enabling)
        # In production, you might want to store this in a temporary cache
        return {
            "secret": secret,
            "qr_code": qr_code,
            "uri": uri
        }
    
    @staticmethod
    def enable_2fa(
        db: Session,
        user_id: str,
        secret: str,
        verification_code: str
    ) -> list[str]:
        """Enable 2FA for a user after verification"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        
        # Verify the code
        if not verify_2fa_code(secret, verification_code):
            raise ValueError("Invalid verification code")
        
        # Encrypt and store the secret
        user.two_fa_secret = encrypt_data(secret)
        user.two_fa_enabled = True
        
        # Generate backup codes
        backup_codes = generate_backup_codes()
        # In production, you'd want to hash and store these
        
        from sqlalchemy.orm import Session as SQLSession
        db: SQLSession = db
        db.commit()
        db.refresh(user)
        
        return backup_codes
    
    @staticmethod
    def disable_2fa(db: Session, user_id: str) -> bool:
        """Disable 2FA for a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.two_fa_enabled = False
        user.two_fa_secret = None
        db.commit()
        return True
    
    @staticmethod
    def verify_2fa(db: Session, user_id: str, code: str) -> bool:
        """Verify a 2FA code for a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.two_fa_enabled:
            return False
        
        secret = decrypt_data(user.two_fa_secret)
        return verify_2fa_code(secret, code)


