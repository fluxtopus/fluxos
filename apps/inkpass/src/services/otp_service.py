"""OTP service for password reset and email verification"""

from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import hashlib
from src.database.models import User, OTPCode


def generate_otp_code() -> str:
    """Generate a 6-digit OTP code"""
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp_code(code: str) -> str:
    """Hash an OTP code for storage"""
    return hashlib.sha256(code.encode()).hexdigest()


class OTPService:
    """OTP service"""
    
    @staticmethod
    def create_otp(
        db: Session,
        user_id: str,
        purpose: str,
        expires_minutes: int = 10
    ) -> str:
        """Create an OTP code for a user"""
        code = generate_otp_code()
        code_hash = hash_otp_code(code)
        
        otp = OTPCode(
            user_id=user_id,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes)
        )
        db.add(otp)
        db.commit()
        
        return code
    
    @staticmethod
    def verify_otp(
        db: Session,
        user_id: str,
        code: str,
        purpose: str
    ) -> bool:
        """Verify an OTP code"""
        code_hash = hash_otp_code(code)
        
        otp = db.query(OTPCode).filter(
            OTPCode.user_id == user_id,
            OTPCode.code_hash == code_hash,
            OTPCode.purpose == purpose,
            OTPCode.expires_at > datetime.utcnow(),
            OTPCode.used_at.is_(None)
        ).first()
        
        if not otp:
            return False
        
        # Mark as used
        otp.used_at = datetime.utcnow()
        db.commit()
        
        return True
    
    @staticmethod
    def invalidate_user_otps(db: Session, user_id: str, purpose: str) -> None:
        """Invalidate all unused OTPs for a user and purpose"""
        db.query(OTPCode).filter(
            OTPCode.user_id == user_id,
            OTPCode.purpose == purpose,
            OTPCode.used_at.is_(None)
        ).update({"used_at": datetime.utcnow()})
        db.commit()


