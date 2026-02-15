"""OAuth authentication routes"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from src.database.database import get_db
from src.services.oauth_service import OAuthService
from src.services.oauth.provider_interface import OAuthError
from src.config import settings


router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])


class OAuthProviderResponse(BaseModel):
    """Response for OAuth provider info"""
    id: str
    provider_name: str
    authorization_url: str
    is_active: bool
    scopes: list[str]


class OAuthCallbackRequest(BaseModel):
    """Request for OAuth callback"""
    code: str
    state: str
    provider: str


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.get("/providers", response_model=list[OAuthProviderResponse])
async def list_oauth_providers(db: Session = Depends(get_db)):
    """
    List all active OAuth providers.

    Returns list of available OAuth providers (Google, Apple, etc.)
    that users can authenticate with.
    """
    service = OAuthService(db)
    providers = service.list_active_providers()

    return [
        OAuthProviderResponse(
            id=p.id,
            provider_name=p.provider_name,
            authorization_url=p.authorization_url,
            is_active=p.is_active,
            scopes=p.scopes or []
        )
        for p in providers
    ]


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    db: Session = Depends(get_db)
):
    """
    Initiate OAuth login flow.

    Redirects user to OAuth provider's authorization page.
    State token is stored in cookie for CSRF protection.

    Args:
        provider: OAuth provider name (e.g., "google", "apple")

    Returns:
        Redirect to OAuth provider's authorization URL
    """
    try:
        service = OAuthService(db)
        auth_url, state = service.initiate_oauth_flow(
            provider_name=provider,
            redirect_uri=settings.OAUTH_REDIRECT_URI
        )

        redirect_response = RedirectResponse(url=auth_url)

        # Store state in cookie for CSRF protection
        redirect_response.set_cookie(
            key=settings.OAUTH_STATE_COOKIE_NAME,
            value=state,
            max_age=settings.OAUTH_STATE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=settings.APP_ENV == "production"
        )

        return redirect_response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/callback")
async def oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
    provider: Optional[str] = None  # Some providers don't include this
):
    """
    OAuth callback endpoint.

    This is where the OAuth provider redirects after user authorizes.
    Exchanges authorization code for tokens and creates/links user account.

    Query params:
        code: Authorization code from OAuth provider
        state: CSRF protection token
        provider: Provider name (optional, some providers include this)

    Returns:
        JWT tokens for authenticated user
    """
    # Verify state token for CSRF protection
    stored_state = request.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    if not stored_state or not hmac.compare_digest(stored_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token. Possible CSRF attack."
        )

    # Determine provider from state or query param
    # For now, we'll need to extract provider from the request
    # In production, you might encode provider in the state token
    if not provider:
        # Try to determine from referer or store in state
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider not specified"
        )

    try:
        service = OAuthService(db)
        user, tokens = await service.complete_oauth_flow(
            provider_name=provider,
            code=code,
            redirect_uri=settings.OAUTH_REDIRECT_URI
        )

        response = JSONResponse(content=TokenResponse(**tokens).model_dump())
        response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME)
        return response

    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth authentication failed: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )


@router.post("/callback", response_model=TokenResponse)
async def oauth_callback_post(
    request_data: OAuthCallbackRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    OAuth callback endpoint (POST version).

    Alternative callback method for providers that POST the authorization code.
    Also useful for mobile apps that want to handle OAuth in-app.

    Body:
        code: Authorization code from OAuth provider
        state: CSRF protection token
        provider: Provider name

    Returns:
        JWT tokens for authenticated user
    """
    # Verify state token for CSRF protection
    stored_state = request.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    if not stored_state or not hmac.compare_digest(stored_state, request_data.state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token. Possible CSRF attack."
        )

    try:
        service = OAuthService(db)
        user, tokens = await service.complete_oauth_flow(
            provider_name=request_data.provider,
            code=request_data.code,
            redirect_uri=settings.OAUTH_REDIRECT_URI
        )

        response = JSONResponse(content=TokenResponse(**tokens).model_dump())
        response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME)
        return response

    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth authentication failed: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )
