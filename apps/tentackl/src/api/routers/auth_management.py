# REVIEW:
# - Router mixes direct InkPass SDK calls and raw HTTP proxying; duplicated error handling and inconsistent patterns.
# - Hard-coded INKPASS_URL lookups repeated per endpoint; should be centralized in a client/service.
# - Imports scope constants (Scopes/READONLY_SCOPES/etc.) but authorization is now InkPass-based; legacy surface lingers.
"""API routes for authentication management."""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import structlog
import asyncio

from src.application.auth import AuthUseCases
from src.api.auth_middleware import (
    auth_middleware, AuthUser, Scopes,
    READONLY_SCOPES, OPERATOR_SCOPES, DEVELOPER_SCOPES,
)
from src.api.error_helpers import safe_error_detail
from src.infrastructure.auth import AuthServiceAdapter

# Import InkPass SDK exceptions conditionally — they're only raised when
# the InkPass backend is active, but the router error handlers need them.
try:
    from inkpass_sdk.exceptions import (
        AuthenticationError,
        PermissionDeniedError,
        ValidationError,
        ServiceUnavailableError,
        ResourceNotFoundError,
    )
except ImportError:
    # Standalone mode: define stubs so except clauses don't break.
    # These will never be raised when InkPass is not installed.
    class AuthenticationError(Exception): pass  # type: ignore[no-redef]
    class PermissionDeniedError(Exception): pass  # type: ignore[no-redef]
    class ValidationError(Exception): pass  # type: ignore[no-redef]
    class ServiceUnavailableError(Exception): pass  # type: ignore[no-redef]
    class ResourceNotFoundError(Exception): pass  # type: ignore[no-redef]

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def get_auth_use_cases() -> AuthUseCases:
    """Provide application-layer auth use cases."""
    return AuthUseCases(auth_ops=AuthServiceAdapter())


class CreateAPIKeyRequest(BaseModel):
    """Request to create an API key via InkPass."""
    name: str = Field(..., description="Name for the API key")
    scopes: Optional[List[str]] = Field(None, description="List of scopes")


class CreateAPIKeyResponse(BaseModel):
    """Response from creating an API key."""
    id: str
    key: str
    name: str
    scopes: List[str]
    message: str = "Store this API key securely. It won't be shown again."


class TokenRequest(BaseModel):
    """Request to create a token."""
    username: str
    password: str  # In production, validate against user database
    scopes: Optional[List[str]] = None
    

class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str = Field(..., description="Refresh token")


class RevokeAPIKeyRequest(BaseModel):
    """Request to revoke an API key."""
    api_key: str = Field(..., description="The API key to revoke")


class RegisterRequest(BaseModel):
    """Request to register a new user."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    first_name: Optional[str] = Field(None, description="User first name")
    last_name: Optional[str] = Field(None, description="User last name")
    organization_name: Optional[str] = Field(None, description="Organization name (optional)")


class RegisterResponse(BaseModel):
    """Response from user registration."""
    user_id: str
    email: str
    organization_id: str
    message: str = "User registered successfully"


class VerifyEmailRequest(BaseModel):
    """Request to verify email with OTP code."""
    email: str = Field(..., description="User email address")
    code: str = Field(..., description="6-digit verification code")


class VerifyEmailResponse(BaseModel):
    """Response from email verification."""
    message: str


class ResendVerificationRequest(BaseModel):
    """Request to resend verification email."""
    email: str = Field(..., description="User email address")


@router.post("/token", response_model=TokenResponse)
async def create_token(
    request: TokenRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Create an access token for user authentication.

    This endpoint authenticates users via inkPass and returns a JWT token.
    """
    try:
        # Authenticate with inkPass (username is treated as email)
        tokens = await use_cases.login(email=request.username, password=request.password)

        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        logger.info("User authenticated via inkPass", email=request.username)

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in
        )

    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Login is not available in standalone mode"
        )
    except AuthenticationError as e:
        logger.warning("Authentication failed", email=request.username, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    except ServiceUnavailableError as e:
        logger.error("Auth service unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable"
        )
    except Exception as e:
        logger.error("Login error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Register a new user via inkPass.

    This endpoint creates a new user account in inkPass.
    """
    try:
        # Register user with inkPass
        registration = await use_cases.register_user(
            email=request.email,
            password=request.password,
            organization_name=request.organization_name,
            first_name=request.first_name,
            last_name=request.last_name,
        )

        logger.info(
            "User registered via inkPass",
            email=request.email,
            user_id=registration["user_id"],
            organization_id=registration["organization_id"]
        )

        return RegisterResponse(
            user_id=registration["user_id"],
            email=registration["email"],
            organization_id=registration["organization_id"]
        )

    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="User registration is not available in standalone mode"
        )
    except ValidationError as e:
        logger.warning("Registration validation failed", email=request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_error_detail(str(e))
        )
    except ServiceUnavailableError as e:
        logger.error("Auth service unavailable during registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service temporarily unavailable"
        )
    except Exception as e:
        logger.error("Registration error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    request: VerifyEmailRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Verify email address with OTP code.

    This endpoint verifies a user's email using the OTP code sent during registration.
    """
    try:
        result = await use_cases.verify_email(request.email, request.code)
        logger.info("Email verified via inkPass", email=request.email)
        return VerifyEmailResponse(message=result.get("message", "Email verified successfully"))

    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Email verification is not available in standalone mode"
        )
    except ValidationError as e:
        logger.warning("Email verification failed", email=request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e))
        )
    except ResourceNotFoundError as e:
        logger.warning("User not found for email verification", email=request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    except ServiceUnavailableError as e:
        logger.error("Auth service unavailable during email verification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service temporarily unavailable"
        )
    except Exception as e:
        logger.error("Email verification error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/resend-verification", response_model=VerifyEmailResponse)
async def resend_verification(
    request: ResendVerificationRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Resend email verification code.

    This endpoint sends a new verification code to the user's email.
    """
    try:
        result = await use_cases.resend_verification(request.email)
        logger.info("Verification code resent via inkPass", email=request.email)
        return VerifyEmailResponse(message=result.get("message", "Verification code sent"))

    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Email verification is not available in standalone mode"
        )
    except ServiceUnavailableError as e:
        logger.error("Auth service unavailable during resend verification", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service temporarily unavailable"
        )
    except Exception as e:
        logger.error("Resend verification error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset."""
    email: str = Field(..., description="User email address")


class ResetPasswordRequest(BaseModel):
    """Request to reset password with OTP."""
    email: str = Field(..., description="User email address")
    code: str = Field(..., description="6-digit reset code")
    new_password: str = Field(..., description="New password")


class UpdateProfileRequest(BaseModel):
    """Request to update user profile."""
    first_name: Optional[str] = Field(None, description="User first name")
    last_name: Optional[str] = Field(None, description="User last name")


class InitiateEmailChangeRequest(BaseModel):
    """Request to initiate email change."""
    new_email: str = Field(..., description="New email address")


class ConfirmEmailChangeRequest(BaseModel):
    """Request to confirm email change with OTP."""
    code: str = Field(..., description="6-digit verification code")


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Initiate forgot password flow."""
    try:
        return await use_cases.forgot_password(request.email)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Forgot password is not available in standalone mode",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError as e:
        logger.error("Forgot password unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Forgot password error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Reset password with OTP verification code."""
    try:
        return await use_cases.reset_password(
            email=request.email,
            code=request.code,
            new_password=request.new_password,
        )
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Password reset is not available in standalone mode",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError as e:
        logger.error("Reset password unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Reset password error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.patch("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Update user profile."""
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await use_cases.update_profile(
            token=token,
            first_name=request.first_name,
            last_name=request.last_name,
        )
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Profile update is not available in standalone mode",
        )
    except (AuthenticationError, PermissionDeniedError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e)),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError as e:
        logger.error("Profile update unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Profile update error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/email-change/initiate")
async def initiate_email_change(
    request: InitiateEmailChangeRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Initiate email change for current user."""
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await use_cases.initiate_email_change(token=token, new_email=request.new_email)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Email change is not available in standalone mode",
        )
    except (AuthenticationError, PermissionDeniedError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e)),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError as e:
        logger.error("Email change initiation unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Email change initiate error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/email-change/confirm")
async def confirm_email_change(
    request: ConfirmEmailChangeRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Confirm email change with verification code."""
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await use_cases.confirm_email_change(token=token, code=request.code)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Email change is not available in standalone mode",
        )
    except (AuthenticationError, PermissionDeniedError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e)),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError as e:
        logger.error("Email change confirm unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Email change confirm error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    refresh_token: str,
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Refresh access token using a refresh token.

    This endpoint proxies the refresh request to inkPass.
    """
    try:
        data = await use_cases.refresh_access_token(refresh_token)
        logger.info("Token refreshed via auth use case")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in", 1800),
        )
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Token refresh is not available in standalone mode",
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Token refresh error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/api-keys",
    response_model=CreateAPIKeyResponse,
    dependencies=[Depends(auth_middleware.require_auth())]
)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Create a new API key via InkPass.

    Requires a Bearer token (forwarded to InkPass).
    """
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required to create API keys",
        )

    try:
        result = await use_cases.create_api_key(
            token=token,
            name=request.name,
            scopes=request.scopes,
        )

        logger.info(
            "API key created via InkPass",
            name=request.name,
            key_id=result["id"],
            created_by=current_user.id,
        )

        return CreateAPIKeyResponse(
            id=result["id"],
            key=result["key"],
            name=result["name"],
            scopes=result["scopes"] or [],
        )

    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="API key creation is not available in standalone mode",
        )
    except (AuthenticationError, PermissionDeniedError) as e:
        logger.warning("API key creation denied", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied to create API keys",
        )
    except Exception as e:
        logger.error("Failed to create API key", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )


@router.post(
    "/api-keys/revoke",
    dependencies=[Depends(auth_middleware.require_auth())]
)
async def revoke_api_key(
    request: RevokeAPIKeyRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Revoke an API key via InkPass.

    Requires a Bearer token (forwarded to InkPass).
    """
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required to revoke API keys",
        )

    try:
        result = await use_cases.revoke_api_key(token=token, api_key=request.api_key)

        logger.info("API key revoked via InkPass", revoked_by=current_user.id)
        return result
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="API key revocation is not available in standalone mode",
        )
    except ResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    except (AuthenticationError, PermissionDeniedError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e)),
        )
    except ServiceUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    except Exception as e:
        logger.error("Failed to revoke API key", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key",
        )


@router.get("/me")
async def get_current_user(
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """Get information about the current authenticated user/service."""
    # Get email from metadata if available (for inkPass users), else use username
    email = current_user.metadata.get("email") if current_user.metadata else None
    email = email or current_user.username

    first_name = current_user.metadata.get("first_name") if current_user.metadata else None
    last_name = current_user.metadata.get("last_name") if current_user.metadata else None

    # If name fields are missing (e.g. from local JWT decode), fetch from InkPass
    if not first_name and not last_name and current_user.metadata and current_user.metadata.get("inkpass_validated"):
        try:
            token = current_user.metadata.get("token")
            if token and use_cases.supports_user_management:
                inkpass_user = await use_cases.get_user_info(token)
                if inkpass_user:
                    first_name = inkpass_user.get("first_name")
                    last_name = inkpass_user.get("last_name")
        except Exception as e:
            logger.warning("Failed to fetch user info", error=str(e))

    return {
        "id": current_user.id,
        "email": email,
        "auth_type": current_user.auth_type,
        "username": current_user.username,
        "first_name": first_name,
        "last_name": last_name,
        "service_name": current_user.service_name,
        "scopes": current_user.scopes,
        "organization_id": current_user.metadata.get("organization_id") if current_user.metadata else None,
        "metadata": current_user.metadata
    }


@router.get("/scopes")
async def list_available_scopes():
    """List all available API scopes."""
    return {
        "scopes": {
            "workflow": [
                {"name": Scopes.WORKFLOW_READ, "description": "Read workflow data"},
                {"name": Scopes.WORKFLOW_WRITE, "description": "Create and modify workflows"},
                {"name": Scopes.WORKFLOW_DELETE, "description": "Delete workflows"},
                {"name": Scopes.WORKFLOW_EXECUTE, "description": "Execute workflows"},
                {"name": Scopes.WORKFLOW_CONTROL, "description": "Control workflow state (pause/resume/signal)"},
            ],
            "agent": [
                {"name": Scopes.AGENT_READ, "description": "Read agent data"},
                {"name": Scopes.AGENT_WRITE, "description": "Create and modify agents"},
                {"name": Scopes.AGENT_EXECUTE, "description": "Execute agents"},
            ],
            "event": [
                {"name": Scopes.EVENT_READ, "description": "Read events"},
                {"name": Scopes.EVENT_PUBLISH, "description": "Publish events"},
                {"name": Scopes.WEBHOOK_PUBLISH, "description": "Publish webhook events"},
            ],
            "metrics": [
                {"name": Scopes.METRICS_READ, "description": "Read metrics data"},
                {"name": Scopes.METRICS_ADMIN, "description": "Administer metrics (create alerts, configure monitoring)"},
            ],
            "other": [
                {"name": Scopes.ADMIN, "description": "Full administrative access"},
            ]
        },
        "permission_groups": {
            "readonly": {
                "description": "Read-only access to resources",
                "scopes": READONLY_SCOPES
            },
            "operator": {
                "description": "Operate and control workflows",
                "scopes": OPERATOR_SCOPES
            },
            "developer": {
                "description": "Full development access",
                "scopes": DEVELOPER_SCOPES
            },
            "admin": {
                "description": "Administrative access",
                "scopes": [Scopes.ADMIN]
            }
        }
    }


# Health check endpoint (no auth required)
@router.get("/health")
async def auth_health():
    """Check authentication service health."""
    return {"status": "healthy", "service": "authentication"}


class PermissionCheckResponse(BaseModel):
    """Response from permission check."""
    has_permission: bool
    user_id: str
    organization_id: Optional[str] = None


class PermissionSpec(BaseModel):
    """Permission spec for batch checks."""
    resource: str
    action: str


class PermissionBatchRequest(BaseModel):
    """Request to check multiple permissions."""
    permissions: List[PermissionSpec]
    context: Optional[Dict[str, Any]] = None


class PermissionBatchResponse(BaseModel):
    """Response from batch permission checks."""
    permissions: Dict[str, bool]


@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    resource: str,
    action: str,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Check if the current user has a specific permission.

    This endpoint proxies the permission check to InkPass.
    Used by the frontend to conditionally show/hide UI elements.

    Args:
        resource: The resource to check (e.g., "capabilities", "agents")
        action: The action to check (e.g., "manage", "view", "create")
    """
    # For inkPass-validated users, check permission via inkPass
    if current_user.metadata and current_user.metadata.get("inkpass_validated"):
        token = current_user.metadata.get("token")
        if not token:
            return PermissionCheckResponse(
                has_permission=False,
                user_id=current_user.id,
                organization_id=current_user.metadata.get("organization_id")
            )

        has_permission = await use_cases.check_permission(
            token=token,
            resource=resource,
            action=action,
            context=None
        )
        return PermissionCheckResponse(
            has_permission=has_permission,
            user_id=current_user.id,
            organization_id=current_user.metadata.get("organization_id")
        )

    # For API key auth, check scopes (legacy system)
    if current_user.auth_type == "api_key":
        # API keys use scope-based permissions
        scope_name = f"{resource}:{action}"
        has_perm = scope_name in current_user.scopes or "admin" in current_user.scopes
        return PermissionCheckResponse(
            has_permission=has_perm,
            user_id=current_user.id,
            organization_id=None
        )

    # Default: no permission
    return PermissionCheckResponse(
        has_permission=False,
        user_id=current_user.id,
        organization_id=current_user.metadata.get("organization_id") if current_user.metadata else None
    )


@router.post("/check-batch", response_model=PermissionBatchResponse)
async def check_permissions_batch(
    request: PermissionBatchRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AuthUseCases = Depends(get_auth_use_cases),
):
    """
    Check multiple permissions in a single request.

    Returns a map keyed by "resource:action".
    """
    if not request.permissions:
        return PermissionBatchResponse(permissions={})

    if current_user.auth_type == "api_key":
        scope_set = set(current_user.scopes or [])
        permissions_map: Dict[str, bool] = {}
        for spec in request.permissions:
            scope_name = f"{spec.resource}:{spec.action}"
            permissions_map[scope_name] = scope_name in scope_set or "admin" in scope_set
        return PermissionBatchResponse(permissions=permissions_map)

    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    async def _check(spec: PermissionSpec) -> bool:
        return await use_cases.check_permission(
            token=token,
            resource=spec.resource,
            action=spec.action,
            context=request.context
        )

    results = await asyncio.gather(*[_check(spec) for spec in request.permissions])
    permissions_map = {
        f"{spec.resource}:{spec.action}": result
        for spec, result in zip(request.permissions, results)
    }
    return PermissionBatchResponse(permissions=permissions_map)
