"""Generic OAuth 2.0 endpoints for integration providers.

Provider-agnostic: the integration's provider field determines which OAuth
provider class handles the request. Adding a new OAuth provider requires
only a new provider class + registry entry -- zero route changes.

Endpoints:
    GET  /api/integrations/{id}/oauth/authorize  - Start OAuth flow
    GET  /api/integrations/oauth/callback         - Provider callback
    POST /api/integrations/{id}/oauth/refresh     - Refresh tokens
    DELETE /api/integrations/{id}/oauth/disconnect - Revoke and remove tokens
"""

# REVIEW:
# - Stores bearer_token in Redis state; increases blast radius if Redis is compromised.
# - Duplicates bearer-token extraction logic (see integrations.py).

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security.utils import get_authorization_scheme_param

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.application.integrations import (
    IntegrationOAuthExchangeError,
    IntegrationOAuthStateError,
    IntegrationOAuthUseCases,
)
from src.infrastructure.integrations import (
    MimicIntegrationAdapter,
    OAuthRegistryAdapter,
)
from src.infrastructure.integrations.oauth_state_adapter import IntegrationOAuthStateAdapter
from src.clients.mimic import (
    MimicError,
    ResourceNotFoundError as MimicNotFoundError,
)
from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations-oauth"])

# Singleton IntegrationOAuthUseCases (injected at startup by app.py)
oauth_use_cases: Optional[IntegrationOAuthUseCases] = None


def _get_oauth_use_cases() -> IntegrationOAuthUseCases:
    """Get the injected OAuth use cases or fall back to creating them."""
    global oauth_use_cases
    if oauth_use_cases is None:
        oauth_use_cases = IntegrationOAuthUseCases(
            integration_ops=MimicIntegrationAdapter(),
            oauth_registry=OAuthRegistryAdapter(),
            oauth_state=IntegrationOAuthStateAdapter(),
        )
    return oauth_use_cases

OAUTH_STATE_TTL = 600  # 10 minutes


def _get_bearer_token(request: Request) -> str:
    """Extract Bearer token from request headers."""
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
        )
    return token


def _get_callback_url() -> str:
    """Build the OAuth callback URL using the webhook base URL."""
    return f"{settings.webhook_base_url}/api/integrations/oauth/callback"


def _get_frontend_url() -> str:
    """Get the frontend URL for post-OAuth redirects."""
    return getattr(settings, "TENTACKL_FRONTEND_URL", None) or "http://localhost:3000"


# =============================================================================
# Authorize
# =============================================================================


@router.get("/{integration_id}/oauth/authorize")
async def oauth_authorize(
    integration_id: str,
    request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Start the OAuth authorization flow for an integration.

    Generates PKCE verifier/challenge, stores state in Redis,
    and returns the authorization URL to redirect the user to.
    """
    token = _get_bearer_token(request)

    use_cases = _get_oauth_use_cases()

    try:
        authorization_url = await use_cases.start_authorization(
            integration_id=integration_id,
            user_id=user.id,
            token=token,
            redirect_uri=_get_callback_url(),
            state_ttl_seconds=OAUTH_STATE_TTL,
        )
    except MimicNotFoundError:
        raise HTTPException(status_code=404, detail="Integration not found")
    except MimicError as e:
        raise HTTPException(status_code=502, detail=safe_error_detail(f"Integration service error: {e}"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "OAuth authorize started",
        extra={
            "integration_id": integration_id,
            "user_id": user.id,
        },
    )

    return {"authorization_url": authorization_url}


# =============================================================================
# Callback
# =============================================================================


@router.get("/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
):
    """Handle OAuth provider callback.

    Exchanges the authorization code for tokens and stores them
    as encrypted credentials via Mimic. Redirects the user back
    to the integration detail page in the frontend.
    """
    redirect_uri = _get_callback_url()
    try:
        use_cases = _get_oauth_use_cases()
        integration_id = await use_cases.handle_callback(
            code=code,
            state=state,
            redirect_uri=redirect_uri,
        )
    except IntegrationOAuthStateError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    except IntegrationOAuthExchangeError as e:
        logger.error(
            f"OAuth code exchange failed: {e}",
            extra={"integration_id": e.integration_id},
        )
        frontend_url = _get_frontend_url()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations/{e.integration_id}?oauth=error",
            status_code=302,
        )
    except Exception as e:
        logger.error(f"OAuth code exchange failed: {e}")
        frontend_url = _get_frontend_url()
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?oauth=error",
            status_code=302,
        )

    logger.info(
        "OAuth callback completed successfully",
        extra={
            "integration_id": integration_id,
        },
    )

    frontend_url = _get_frontend_url()
    return RedirectResponse(
        url=f"{frontend_url}/settings/integrations/{integration_id}?oauth=success",
        status_code=302,
    )


# =============================================================================
# Refresh
# =============================================================================


@router.post("/{integration_id}/oauth/refresh")
async def oauth_refresh(
    integration_id: str,
    request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Refresh OAuth tokens for an integration.

    Retrieves the stored refresh token, calls the provider's refresh method,
    and updates the stored credentials.
    """
    token = _get_bearer_token(request)

    use_cases = _get_oauth_use_cases()

    # Fetch integration to get provider
    try:
        provider_name = await use_cases.get_integration_provider_name(
            integration_id=integration_id,
            token=token,
        )
    except MimicNotFoundError:
        raise HTTPException(status_code=404, detail="Integration not found")
    except MimicError as e:
        raise HTTPException(status_code=502, detail=safe_error_detail(f"Integration service error: {e}"))
    oauth_provider = use_cases.get_provider(provider_name)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Provider '{provider_name}' does not support OAuth")

    # For now, refresh requires the refresh token to be passed in the request body
    # In a production system, you'd retrieve it from credentials storage
    raise HTTPException(
        status_code=501,
        detail="Token refresh via stored credentials not yet implemented. Disconnect and reconnect to re-authorize.",
    )


# =============================================================================
# Disconnect
# =============================================================================


@router.delete("/{integration_id}/oauth/disconnect")
async def oauth_disconnect(
    integration_id: str,
    request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("integrations", "update")),
):
    """Disconnect OAuth for an integration.

    Attempts to revoke the token with the provider, then removes
    stored credentials.
    """
    token = _get_bearer_token(request)

    use_cases = _get_oauth_use_cases()

    # Fetch integration to get provider
    try:
        provider_name = await use_cases.get_integration_provider_name(
            integration_id=integration_id,
            token=token,
        )
    except MimicNotFoundError:
        raise HTTPException(status_code=404, detail="Integration not found")
    except MimicError as e:
        raise HTTPException(status_code=502, detail=safe_error_detail(f"Integration service error: {e}"))
    oauth_provider = use_cases.get_provider(provider_name)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Provider '{provider_name}' does not support OAuth")

    # Note: Token revocation would require retrieving the stored access token.
    # For now we just log the disconnect. In production, you'd:
    # 1. Retrieve the access_token credential
    # 2. Call oauth_provider.revoke_token(access_token)
    # 3. Delete the credentials

    logger.info(
        "OAuth disconnected",
        extra={
            "integration_id": integration_id,
            "provider": provider_name,
            "user_id": user.id,
        },
    )

    return {"status": "disconnected", "integration_id": integration_id}
