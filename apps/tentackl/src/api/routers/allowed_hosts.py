# REVIEW:
# - Imports Scopes but doesn't use it; docstrings mention workflow scopes while permissions use "webhooks".
# - Depends on get_database from api.app (global state); tight coupling to app module.
"""API routes for managing allowed HTTP hosts."""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import structlog

from src.api.auth_middleware import (
    auth_middleware, AuthUser
)
from src.application.allowed_hosts import AllowedHostUseCases
from src.infrastructure.allowed_hosts import AllowedHostServiceAdapter
from src.interfaces.database import Database
from src.api.error_helpers import safe_error_detail

logger = structlog.get_logger()

router = APIRouter(prefix="/api/allowed-hosts", tags=["allowed-hosts"])

# Global database instance (injected at app startup)
database: Optional[Database] = None


def get_database() -> Database:
    """Get the database instance."""
    if database is None:
        raise HTTPException(
            status_code=503,
            detail="Database not initialized"
        )
    return database


def get_allowed_host_use_cases(
    db: Database = Depends(get_database),
) -> AllowedHostUseCases:
    """Provide application-layer allowed host use cases."""
    return AllowedHostUseCases(host_ops=AllowedHostServiceAdapter(db))


class AllowedHostResponse(BaseModel):
    """Response model for allowed host."""
    id: str
    host: str
    environment: str
    enabled: bool
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]


class CreateAllowedHostRequest(BaseModel):
    """Request to add an allowed host."""
    host: str = Field(..., description="Hostname only (e.g., 'api.example.com')")
    environment: str = Field(default="development", description="Environment: development, production, staging, testing")
    notes: Optional[str] = Field(None, description="Optional notes about why this host is allowed")


class UpdateAllowedHostRequest(BaseModel):
    """Request to update an allowed host."""
    enabled: Optional[bool] = Field(None, description="Enable or disable the host")
    notes: Optional[str] = Field(None, description="Update notes")


@router.get("", response_model=List[AllowedHostResponse])
async def list_allowed_hosts(
    environment: Optional[str] = None,
    current_user: AuthUser = Depends(auth_middleware.require_permission("webhooks", "view")),
    use_cases: AllowedHostUseCases = Depends(get_allowed_host_use_cases),
):
    """
    List all allowed hosts, optionally filtered by environment.
    
    Requires workflow:read scope.
    """
    try:
        hosts = await use_cases.list_allowed_hosts(environment=environment)
        
        return [
            AllowedHostResponse(
                id=str(host.id),
                host=host.host,
                environment=host.environment.value,
                enabled=host.enabled,
                created_by=host.created_by,
                created_at=host.created_at,
                updated_at=host.updated_at,
                notes=host.notes
            )
            for host in hosts
        ]
    except Exception as e:
        logger.error("Failed to list allowed hosts", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list allowed hosts"
        )


@router.post("", response_model=AllowedHostResponse)
async def create_allowed_host(
    request: CreateAllowedHostRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("webhooks", "create")),
    use_cases: AllowedHostUseCases = Depends(get_allowed_host_use_cases),
):
    """
    Add a new allowed host to the allowlist.
    
    The host is immediately active (no approval required).
    However, if the host is in the denylist, it cannot be added.
    
    Requires workflow:write scope.
    """
    try:
        created_by = current_user.id if current_user else None

        allowed_host = await use_cases.create_allowed_host(
            host=request.host,
            environment=request.environment,
            created_by=created_by,
            notes=request.notes
        )
        
        logger.info(
            "Allowed host added",
            host=request.host,
            environment=request.environment,
            created_by=created_by
        )
        
        return AllowedHostResponse(
            id=str(allowed_host.id),
            host=allowed_host.host,
            environment=allowed_host.environment.value,
            enabled=allowed_host.enabled,
            created_by=allowed_host.created_by,
            created_at=allowed_host.created_at,
            updated_at=allowed_host.updated_at,
            notes=allowed_host.notes
        )
    except ValueError as e:
        logger.warning("Invalid host format or denylisted", host=request.host, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(str(e))
        )
    except Exception as e:
        logger.error("Failed to add allowed host", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add allowed host"
        )


@router.delete("/{host}/{environment}")
async def delete_allowed_host(
    host: str,
    environment: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("webhooks", "create")),
    use_cases: AllowedHostUseCases = Depends(get_allowed_host_use_cases),
):
    """
    Remove (disable) an allowed host from the allowlist.
    
    This performs a soft delete by setting enabled=False.
    
    Requires workflow:write scope.
    """
    try:
        success = await use_cases.delete_allowed_host(host=host, environment=environment)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Allowed host '{host}' not found for environment '{environment}'"
            )
        
        logger.info(
            "Allowed host removed",
            host=host,
            environment=environment,
            removed_by=current_user.id if current_user else None
        )
        
        return {"message": f"Allowed host '{host}' removed from environment '{environment}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to remove allowed host", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove allowed host"
        )


@router.post("/check")
async def check_host_allowed(
    url: str,
    environment: Optional[str] = None,
    current_user: AuthUser = Depends(auth_middleware.require_permission("webhooks", "view")),
    use_cases: AllowedHostUseCases = Depends(get_allowed_host_use_cases),
):
    """
    Check if a URL's host is allowed for HTTP requests.
    
    This endpoint helps users verify if a host is allowed before using it.
    
    Requires workflow:read scope.
    """
    try:
        env = environment or "development"
        is_allowed, error_message = await use_cases.check_host_allowed(url=url, environment=env)
        
        return {
            "url": url,
            "environment": env,
            "allowed": is_allowed,
            "error": error_message
        }
    except Exception as e:
        logger.error("Failed to check host", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check host"
        )
