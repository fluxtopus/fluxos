"""
FastAPI integration example for inkPass SDK.

This example shows how to integrate inkPass authentication and
authorization into a FastAPI application.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from inkpass_sdk import InkPassClient, InkPassConfig, AuthenticationError

# Initialize FastAPI app
app = FastAPI(title="Example API with inkPass")

# Initialize inkPass client
inkpass_config = InkPassConfig(base_url="http://inkpass:8000")
inkpass_client = InkPassClient(inkpass_config)

# Security scheme
security = HTTPBearer()


# Dependency: Get current user
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> dict:
    """
    Dependency to get current authenticated user.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        User information dict

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    user = await inkpass_client.validate_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user.model_dump()


# Dependency: Require specific permission
def require_permission(resource: str, action: str):
    """
    Dependency factory to require specific permission.

    Args:
        resource: Resource name (e.g., "workflows")
        action: Action name (e.g., "create", "read", "update", "delete")

    Returns:
        Dependency function that validates permission
    """

    async def permission_checker(
        user: Annotated[dict, Depends(get_current_user)],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    ) -> dict:
        """Check if user has required permission."""
        token = credentials.credentials

        has_permission = await inkpass_client.check_permission(
            token, resource, action
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}",
            )

        return user

    return permission_checker


# Public endpoint (no auth)
@app.get("/")
async def root():
    """Public root endpoint."""
    return {"message": "Welcome to Example API", "auth": "inkPass"}


# Protected endpoint (requires authentication)
@app.get("/me")
async def get_me(user: Annotated[dict, Depends(get_current_user)]):
    """Get current user information."""
    return {"user": user}


# Protected endpoint with permission check
@app.get("/workflows")
async def list_workflows(
    user: Annotated[dict, Depends(require_permission("workflows", "read"))]
):
    """List workflows - requires 'workflows:read' permission."""
    return {
        "workflows": [],
        "user_id": user["id"],
        "organization_id": user.get("organization_id"),
    }


@app.post("/workflows")
async def create_workflow(
    workflow_data: dict,
    user: Annotated[dict, Depends(require_permission("workflows", "create"))],
):
    """Create workflow - requires 'workflows:create' permission."""
    return {
        "workflow": {
            "id": "wf-123",
            "name": workflow_data.get("name"),
            "created_by": user["id"],
        }
    }


@app.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user: Annotated[dict, Depends(require_permission("workflows", "delete"))],
):
    """Delete workflow - requires 'workflows:delete' permission."""
    return {"workflow_id": workflow_id, "deleted": True}


# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Close inkPass client on shutdown."""
    await inkpass_client.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
