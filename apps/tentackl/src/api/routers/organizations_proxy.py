# REVIEW:
# - Simple proxy duplicates auth_management proxy patterns; consider shared InkPass client wrapper.
# - INKPASS_URL read at import time; config changes at runtime won't propagate.
"""Proxy routes for organization management via inkPass."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import httpx
import os
import structlog

from src.api.auth_middleware import auth_middleware, AuthUser

logger = structlog.get_logger()

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

INKPASS_URL = os.getenv("INKPASS_URL", "http://inkpass:8000")


class UpdateOrganizationRequest(BaseModel):
    """Request to update organization."""
    name: Optional[str] = Field(None, description="Organization name")


@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """Proxy get organization to inkPass."""
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{INKPASS_URL}/api/v1/organizations/{org_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json().get("detail", "Failed to get organization")
                )
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get organization proxy error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{org_id}")
async def update_organization(
    org_id: str,
    request: UpdateOrganizationRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """Proxy update organization to inkPass."""
    token = current_user.metadata.get("token") if current_user.metadata else None
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        data = {}
        if request.name is not None:
            data["name"] = request.name
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{INKPASS_URL}/api/v1/organizations/{org_id}",
                json=data,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json().get("detail", "Failed to update organization")
                )
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update organization proxy error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
