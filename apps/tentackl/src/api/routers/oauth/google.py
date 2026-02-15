# REVIEW:
# - OAuth state handling is in plugin layer, while integrations_oauth does it here; inconsistent patterns.
"""API routes for Google OAuth authentication."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import structlog

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.application.oauth import GoogleCalendarAssistantUseCases, GoogleOAuthUseCases
from src.infrastructure.oauth.google_calendar_assistant_adapter import (
    GoogleCalendarAssistantAdapter,
)
from src.infrastructure.oauth.google_oauth_adapter import GoogleOAuthAdapter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/oauth/google", tags=["google-oauth"])


def _get_google_oauth_use_cases() -> GoogleOAuthUseCases:
    """Provide application-layer Google OAuth use cases."""
    return GoogleOAuthUseCases(oauth_ops=GoogleOAuthAdapter())


def _get_calendar_assistant_use_cases() -> GoogleCalendarAssistantUseCases:
    """Provide application-layer calendar assistant use cases."""
    return GoogleCalendarAssistantUseCases(
        assistant_ops=GoogleCalendarAssistantAdapter(),
    )


def _verify_user_id(user_id: str, current_user: AuthUser) -> None:
    """Verify that the requested user_id matches the authenticated user.

    Prevents an attacker from manipulating another user's OAuth tokens.
    """
    if user_id != current_user.id:
        logger.warning(
            "OAuth user_id mismatch",
            requested_user_id=user_id,
            authenticated_user_id=current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot perform OAuth operations for a different user",
        )


class OAuthStartRequest(BaseModel):
    """Request to start OAuth flow."""
    user_id: str = Field(..., description="User ID to associate with OAuth tokens")


class OAuthStartResponse(BaseModel):
    """Response from starting OAuth flow."""
    success: bool
    authorization_url: str
    user_id: str


class OAuthCallbackRequest(BaseModel):
    """Request from OAuth callback."""
    code: str = Field(..., description="Authorization code from Google")
    state: str = Field(..., description="Signed anti-CSRF state token")


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback."""
    success: bool
    user_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class OAuthStatusResponse(BaseModel):
    """Response from OAuth status check."""
    connected: bool
    user_id: str
    token_expired: Optional[bool] = None
    has_refresh_token: Optional[bool] = None
    expires_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


@router.get("/start", response_model=OAuthStartResponse)
async def start_oauth_flow(
    user_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
):
    """
    Start Google OAuth flow and get authorization URL.

    Requires authentication. The user_id must match the authenticated user
    to prevent account-linking attacks.

    Args:
        user_id: User ID to associate with OAuth tokens

    Returns:
        Authorization URL to redirect user to
    """
    _verify_user_id(user_id, current_user)

    try:
        use_cases = _get_google_oauth_use_cases()
        result = await use_cases.start_oauth(user_id=user_id)

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate OAuth URL"
            )

        logger.info("Google OAuth flow started", user_id=user_id)

        return OAuthStartResponse(
            success=result["success"],
            authorization_url=result["authorization_url"],
            user_id=result["user_id"]
        )

    except ValueError as e:
        logger.error("Google OAuth plugin not found", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured"
        )
    except Exception as e:
        logger.error("Failed to start OAuth flow", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.get("/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(code: str, state: str):
    """
    Handle Google OAuth callback.

    Args:
        code: Authorization code from Google
        state: Signed anti-CSRF state token

    Returns:
        User information after successful OAuth
    """
    try:
        use_cases = _get_google_oauth_use_cases()
        result = await use_cases.handle_callback(code=code, state=state)

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete OAuth flow"
            )

        logger.info(
            "Google OAuth callback completed",
            user_id=result["user_id"],
            email=result.get("email")
        )

        return OAuthCallbackResponse(
            success=result["success"],
            user_id=result["user_id"],
            email=result["email"],
            name=result.get("name"),
            picture=result.get("picture")
        )

    except ValueError as e:
        logger.error("Google OAuth plugin not found", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured"
        )
    except Exception as e:
        logger.error("OAuth callback failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.get("/status/{user_id}", response_model=OAuthStatusResponse)
async def get_oauth_status(
    user_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
):
    """
    Check Google OAuth connection status for a user.

    Requires authentication. The user_id must match the authenticated user.

    Args:
        user_id: User ID to check

    Returns:
        Connection status and token information
    """
    _verify_user_id(user_id, current_user)

    try:
        use_cases = _get_google_oauth_use_cases()
        result = await use_cases.get_status(user_id=user_id)

        logger.info(
            "Google OAuth status checked",
            user_id=user_id,
            connected=result.get("connected")
        )

        return OAuthStatusResponse(**result)

    except ValueError as e:
        logger.error("Google OAuth plugin not found", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured"
        )
    except Exception as e:
        logger.error("Failed to check OAuth status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


class CalendarAssistantResponse(BaseModel):
    """Response from calendar assistant enable/disable operations."""
    success: bool
    user_id: str
    enabled: bool
    message: str


@router.post("/enable-assistant", response_model=CalendarAssistantResponse)
async def enable_calendar_assistant(
    user_id: str,
    cron: str = "*/15 * * * *",
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    calendar_use_cases: GoogleCalendarAssistantUseCases = Depends(
        _get_calendar_assistant_use_cases
    ),
):
    """
    Enable calendar assistant for a user.

    Requires authentication. The user_id must match the authenticated user.

    This creates a scheduled automation that runs the calendar assistant task
    on a cron schedule.

    Args:
        user_id: User ID to enable calendar assistant for
        cron: Cron expression for schedule (default: every 15 minutes)

    Returns:
        Confirmation that calendar assistant is enabled
    """
    _verify_user_id(user_id, current_user)

    try:
        # Verify user has Google OAuth connected first
        use_cases = _get_google_oauth_use_cases()
        oauth_status = await use_cases.get_status(user_id=user_id)

        if not oauth_status.get("connected"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth not connected. Please connect Google account first."
            )
        organization_id = None
        if current_user.metadata:
            organization_id = current_user.metadata.get("organization_id")

        result = await calendar_use_cases.enable_assistant(
            user_id=user_id,
            organization_id=organization_id,
            cron=cron,
        )
        return CalendarAssistantResponse(**result)

    except HTTPException:
        raise
    except ValueError as e:
        if "Invalid cron expression" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        logger.error("Google OAuth plugin not found", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured"
        )
    except Exception as e:
        logger.error("Failed to enable calendar assistant", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.post("/disable-assistant", response_model=CalendarAssistantResponse)
async def disable_calendar_assistant(
    user_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    calendar_use_cases: GoogleCalendarAssistantUseCases = Depends(
        _get_calendar_assistant_use_cases
    ),
):
    """
    Disable calendar assistant for a user.

    Requires authentication. The user_id must match the authenticated user.

    This disables the scheduled automation, stopping the calendar assistant
    from running automatically for this user.

    Args:
        user_id: User ID to disable calendar assistant for

    Returns:
        Confirmation that calendar assistant is disabled
    """
    _verify_user_id(user_id, current_user)

    try:
        result = await calendar_use_cases.disable_assistant(user_id=user_id)
        return CalendarAssistantResponse(**result)
    except Exception as e:
        logger.error("Failed to disable calendar assistant", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )
