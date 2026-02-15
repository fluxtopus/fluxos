"""Authentication routes"""

import re
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from typing import Optional
from src.database.database import get_db
from src.services.auth_service import AuthService
from src.services.otp_service import OTPService
from src.services.two_fa_service import TwoFAService
from src.services.notification_service import notification_service
from src.middleware.auth_middleware import security, get_auth_context, AuthContext
from src.middleware.rate_limiting import rate_limit, enforce_rate_limit
from src.database.models import User, Organization

router = APIRouter()

# Rate limit configurations (requests per minute)
RATE_LIMIT_REGISTER = rate_limit("auth:register", limit=3, window=60)
RATE_LIMIT_LOGOUT = rate_limit("auth:logout", limit=10, window=60)
RATE_LIMIT_REFRESH = rate_limit("auth:refresh", limit=10, window=60)
RATE_LIMIT_VERIFY = rate_limit("auth:verify", limit=5, window=60)
RATE_LIMIT_RESEND = rate_limit("auth:resend", limit=3, window=60)
RATE_LIMIT_FORGOT = rate_limit("auth:forgot", limit=3, window=60)
RATE_LIMIT_RESET = rate_limit("auth:reset", limit=5, window=60)
RATE_LIMIT_ME = rate_limit("auth:me", limit=30, window=60)
RATE_LIMIT_2FA = rate_limit("auth:2fa", limit=5, window=60)
RATE_LIMIT_CHECK = rate_limit("auth:check", limit=200, window=60)  # High limit - used for permission checks on every API call
RATE_LIMIT_PROFILE = rate_limit("auth:profile", limit=10, window=60)
RATE_LIMIT_EMAIL_CHANGE = rate_limit("auth:email_change", limit=3, window=60)
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60

# Name validation pattern: letters, accented chars, apostrophes, hyphens, spaces
NAME_PATTERN = re.compile(r"^[\w\s'\-\u00C0-\u024F]+$")
# Org name pattern: alphanumeric, spaces, apostrophes, ampersands, periods, commas, hyphens
ORG_NAME_PATTERN = re.compile(r"^[\w\s'&.,\-\u00C0-\u024F]+$")


def validate_person_name(value: str, field_name: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise ValueError(f"{field_name} must be at least 2 characters")
    if len(value) > 50:
        raise ValueError(f"{field_name} must be at most 50 characters")
    if not NAME_PATTERN.match(value):
        raise ValueError(f"{field_name} contains invalid characters")
    return value


def validate_org_name(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise ValueError("Organization name must be at least 2 characters")
    if len(value) > 100:
        raise ValueError("Organization name must be at most 100 characters")
    if not ORG_NAME_PATTERN.match(value):
        raise ValueError("Organization name contains invalid characters")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    organization_name: Optional[str] = None

    @field_validator('first_name')
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        return validate_person_name(v, "First name")

    @field_validator('last_name')
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        return validate_person_name(v, "Last name")

    @field_validator('organization_name')
    @classmethod
    def validate_organization_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return validate_org_name(v)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    two_fa_code: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator('first_name')
    @classmethod
    def validate_first_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_person_name(v, "First name")
        return v

    @field_validator('last_name')
    @classmethod
    def validate_last_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_person_name(v, "Last name")
        return v


class InitiateEmailChangeRequest(BaseModel):
    new_email: EmailStr


class ConfirmEmailChangeRequest(BaseModel):
    code: str


class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code: str
    uri: str


class TwoFAEnableRequest(BaseModel):
    secret: str
    verification_code: str


class TwoFAVerifyRequest(BaseModel):
    code: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_REGISTER)
):
    """Register a new user"""
    try:
        result = AuthService.register_user(
            db,
            request.email,
            request.password,
            request.organization_name,
            request.first_name,
            request.last_name
        )

        # Create email verification OTP (30 min expiry)
        code = OTPService.create_otp(db, result["user_id"], "email_verification", 30)

        # Get organization for branding
        org = db.query(Organization).filter(Organization.id == result["organization_id"]).first()

        # Send email verification in background
        background_tasks.add_task(
            notification_service.send_email_verification, request.email, code, 30, org
        )

        return {
            **result,
            "message": "Please check your email for the verification code"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration could not be completed"
        )


@router.post("/login")
async def login(
    request: LoginRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """Login and get access token"""
    await enforce_rate_limit(
        request=raw_request,
        key="auth:login",
        limit=LOGIN_RATE_LIMIT,
        window=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        identifier=request.email.lower(),
    )

    try:
        result = AuthService.login_user(
            db,
            request.email,
            request.password,
            request.two_fa_code
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_LOGOUT)
):
    """Logout and invalidate session"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    if not AuthService.logout_by_jwt(db, credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_REFRESH)
):
    """Refresh access token"""
    try:
        result = AuthService.refresh_access_token(db, refresh_token)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_VERIFY)
):
    """Verify email address with OTP code"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not OTPService.verify_otp(db, user.id, request.code, "email_verification"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )

    if user.status == "active":
        return {"message": "Email already verified"}

    # Activate the user
    user.status = "active"
    db.commit()

    # Invalidate all verification OTPs
    OTPService.invalidate_user_otps(db, user.id, "email_verification")

    # Get organization for branding
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    org_name = org.name if org else "Your Organization"

    # Send welcome email now that they're verified
    background_tasks.add_task(
        notification_service.send_welcome_email, request.email, org_name, org
    )

    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    request: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_RESEND)
):
    """Resend email verification code"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        # Don't reveal if user exists
        return {"message": "If the email exists and is unverified, a new code has been sent"}

    if user.status == "active":
        return {"message": "Email already verified"}

    # Invalidate existing verification OTPs
    OTPService.invalidate_user_otps(db, user.id, "email_verification")

    # Create new verification OTP
    code = OTPService.create_otp(db, user.id, "email_verification", 30)

    # Get organization for branding
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    # Send email verification
    background_tasks.add_task(
        notification_service.send_email_verification, request.email, code, 30, org
    )

    return {"message": "Verification code sent"}


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_FORGOT)
):
    """Request password reset OTP"""
    # Always return same message to prevent email enumeration
    response_message = "If an account with this email exists, a password reset code has been sent"

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        return {"message": response_message}

    code = OTPService.create_otp(db, user.id, "reset_password")

    # Get user's organization for branding
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    # Send password reset email in background with organization branding
    background_tasks.add_task(
        notification_service.send_password_reset_email, request.email, code, 10, org
    )

    return {"message": response_message}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_RESET)
):
    """Reset password with OTP"""
    # Use same error message for both cases to prevent email enumeration
    invalid_otp_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset code"
    )

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise invalid_otp_error

    if not OTPService.verify_otp(db, user.id, request.code, "reset_password"):
        raise invalid_otp_error

    # Validate and update password
    from src.security.password import hash_password, validate_password
    from src.services.auth_service import AuthService
    try:
        validate_password(request.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    user.password_hash = hash_password(request.new_password)
    db.commit()

    # Invalidate all sessions (force re-login everywhere)
    sessions_invalidated = AuthService.invalidate_all_user_sessions(db, user.id)

    # Invalidate all OTPs
    OTPService.invalidate_user_otps(db, user.id, "reset_password")

    # Get user's organization for branding
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    # Send password changed confirmation email with organization branding
    background_tasks.add_task(
        notification_service.send_password_changed_email, request.email, org
    )

    return {"message": "Password reset successfully"}


@router.get("/me")
async def get_current_user_info(
    auth_context: AuthContext = Depends(get_auth_context),
    _rate_limit: None = Depends(RATE_LIMIT_ME)
):
    """Get current user or API key information"""
    if auth_context.user:
        return {
            "id": auth_context.user.id,
            "email": auth_context.user.email,
            "first_name": auth_context.user.first_name,
            "last_name": auth_context.user.last_name,
            "organization_id": auth_context.user.organization_id,
            "status": auth_context.user.status,
            "two_fa_enabled": auth_context.user.two_fa_enabled,
            "auth_type": "user"
        }
    elif auth_context.api_key:
        return {
            "id": auth_context.api_key.id,
            "name": auth_context.api_key.name,
            "organization_id": auth_context.api_key.organization_id,
            "user_id": auth_context.api_key.user_id,
            "scopes": auth_context.api_key.scopes,
            "auth_type": "api_key"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )


@router.post("/2fa/setup")
async def setup_2fa(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_2FA)
):
    """Setup 2FA for current user"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    result = TwoFAService.setup_2fa(db, auth_context.user.id)
    return result


@router.post("/2fa/enable")
async def enable_2fa(
    request: TwoFAEnableRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_2FA)
):
    """Enable 2FA after verification"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    try:
        backup_codes = TwoFAService.enable_2fa(
            db,
            auth_context.user.id,
            request.secret,
            request.verification_code
        )

        # Get user's organization for branding
        org = db.query(Organization).filter(
            Organization.id == auth_context.user.organization_id
        ).first()

        # Send 2FA enabled confirmation email with organization branding
        background_tasks.add_task(
            notification_service.send_2fa_enabled_email, auth_context.user.email, org
        )

        return {
            "message": "2FA enabled successfully",
            "backup_codes": backup_codes
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/2fa/disable")
async def disable_2fa(
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_2FA)
):
    """Disable 2FA for current user"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    TwoFAService.disable_2fa(db, auth_context.user.id)

    # Get user's organization for branding
    org = db.query(Organization).filter(
        Organization.id == auth_context.user.organization_id
    ).first()

    # Send 2FA disabled confirmation email with organization branding
    background_tasks.add_task(
        notification_service.send_2fa_disabled_email, auth_context.user.email, org
    )

    return {"message": "2FA disabled successfully"}


@router.post("/2fa/verify")
async def verify_2fa(
    request: TwoFAVerifyRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_2FA)
):
    """Verify 2FA code"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    is_valid = TwoFAService.verify_2fa(db, auth_context.user.id, request.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 2FA code"
        )
    
    return {"message": "2FA code verified"}


@router.post("/2fa/backup-codes")
async def generate_backup_codes(
    auth_context: AuthContext = Depends(get_auth_context),
    _rate_limit: None = Depends(RATE_LIMIT_2FA)
):
    """Generate backup codes for 2FA"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    from src.security.two_fa import generate_backup_codes
    codes = generate_backup_codes()
    return {"backup_codes": codes}


@router.patch("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_PROFILE)
):
    """Update current user's first_name and/or last_name"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user = db.query(User).filter(User.id == auth_context.user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if request.first_name is not None:
        user.first_name = request.first_name
    if request.last_name is not None:
        user.last_name = request.last_name

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "organization_id": user.organization_id,
    }


@router.post("/email-change/initiate")
async def initiate_email_change(
    request: InitiateEmailChangeRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_EMAIL_CHANGE)
):
    """Initiate email change by sending OTP to new email"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    new_email = request.new_email.lower()

    # Check new email is not already taken
    existing = db.query(User).filter(User.email == new_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use"
        )

    # Create OTP with purpose encoding the new email
    purpose = f"email_change:{new_email}"
    code = OTPService.create_otp(db, auth_context.user.id, purpose, 30)

    # Get org for branding
    org = db.query(Organization).filter(
        Organization.id == auth_context.user.organization_id
    ).first()

    # Send verification to the NEW email
    background_tasks.add_task(
        notification_service.send_email_change_verification, new_email, code, 30, org
    )

    return {"message": "Verification code sent to new email address"}


@router.post("/email-change/confirm")
async def confirm_email_change(
    request: ConfirmEmailChangeRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_EMAIL_CHANGE)
):
    """Confirm email change with OTP code"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user = db.query(User).filter(User.id == auth_context.user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Find valid email_change OTP for this user
    from src.database.models import OTPCode
    from datetime import datetime
    otp_records = db.query(OTPCode).filter(
        OTPCode.user_id == user.id,
        OTPCode.purpose.like("email_change:%"),
        OTPCode.used_at.is_(None),
        OTPCode.expires_at > datetime.utcnow()
    ).all()

    verified = False
    new_email = None
    matched_otp = None
    for otp_record in otp_records:
        if OTPService.verify_otp(db, user.id, request.code, otp_record.purpose):
            new_email = otp_record.purpose.replace("email_change:", "", 1)
            matched_otp = otp_record
            verified = True
            break

    if not verified or not new_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )

    # Double-check email not taken (race condition protection)
    existing = db.query(User).filter(User.email == new_email, User.id != user.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use"
        )

    # Update email
    user.email = new_email
    db.commit()

    # Invalidate all sessions (force re-login)
    AuthService.invalidate_all_user_sessions(db, user.id)

    # Invalidate remaining email change OTPs
    for otp_record in otp_records:
        if otp_record.used_at is None:
            otp_record.used_at = datetime.utcnow()
    db.commit()

    return {"message": "Email updated successfully. Please sign in again."}


@router.post("/check")
async def check_permission(
    resource: str,
    action: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_CHECK)
):
    """Check if user has a specific permission (for other services)"""
    if not auth_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user_id = auth_context.user.id
    org_id = auth_context.user.organization_id

    # First check role template system (new system)
    from src.database.models import UserOrganization
    from src.services.role_service import RoleService

    user_org = db.query(UserOrganization).filter(
        UserOrganization.user_id == user_id,
        UserOrganization.organization_id == org_id,
    ).first()

    if user_org:
        # Check via role template (new system)
        if user_org.role_template_id:
            role_service = RoleService(db)
            if role_service.check_user_has_permission(user_id, org_id, resource, action):
                return {
                    "has_permission": True,
                    "user_id": user_id,
                    "organization_id": org_id
                }

        # Legacy: owners have all permissions
        if user_org.role == "owner":
            return {
                "has_permission": True,
                "user_id": user_id,
                "organization_id": org_id
            }

    # Fall back to direct permission check (ABAC system)
    from src.services.permission_service import PermissionService
    has_permission = PermissionService.check_permission(
        db,
        user_id,
        resource,
        action
    )

    return {
        "has_permission": has_permission,
        "user_id": user_id,
        "organization_id": org_id
    }
