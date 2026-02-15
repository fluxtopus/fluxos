"""Authentication middleware"""

from typing import Optional, Callable
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from src.database.database import get_db
from src.services.auth_service import AuthService
from src.services.api_key_service import APIKeyService
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService
from src.database.models import User, APIKey, UserOrganization

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthContext:
    """Authentication context"""
    def __init__(
        self,
        user: Optional[User] = None,
        api_key: Optional[APIKey] = None,
        auth_type: str = "none"
    ):
        self.user = user
        self.api_key = api_key
        self.auth_type = auth_type
    
    @property
    def organization_id(self) -> Optional[str]:
        """Get organization ID from context"""
        if self.user:
            return self.user.organization_id
        if self.api_key:
            return self.api_key.organization_id
        return None


async def get_auth_context(
    request: Request,
    db: Session = Depends(get_db)
) -> AuthContext:
    """Get authentication context from request - use as dependency"""
    # Try JWT token first
    credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
    if credentials:
        try:
            user = AuthService.get_current_user(db, credentials.credentials)
            if user:
                return AuthContext(user=user, auth_type="jwt")
        except Exception:
            pass
    
    # Try API key
    api_key = await api_key_header(request)
    if api_key:
        try:
            db_key = APIKeyService.verify_api_key(db, api_key)
            if db_key:
                return AuthContext(api_key=db_key, auth_type="api_key")
        except Exception:
            pass
    
    return AuthContext(auth_type="none")


def require_permission(resource: str, action: str) -> Callable:
    """
    Dependency factory that requires a specific permission.

    Permission checking uses lazy role-based evaluation:
    1. If user has a role_template_id, check permissions via RoleService
    2. If user is "owner" role (legacy), grant all permissions
    3. Fall back to direct permission check via PermissionService

    Usage:
        @router.post("/users")
        async def create_user(
            _perm: None = Depends(require_permission("users", "create")),
            auth_context: AuthContext = Depends(get_auth_context),
            db: Session = Depends(get_db)
        ):
    """
    async def check_permission(
        auth_context: AuthContext = Depends(get_auth_context),
        db: Session = Depends(get_db)
    ) -> None:
        if not auth_context.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        user_id = auth_context.user.id
        org_id = auth_context.user.organization_id

        # Get user's organization membership
        user_org = db.query(UserOrganization).filter(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == org_id,
        ).first()

        if user_org:
            # Check via role template (new system with lazy evaluation)
            if user_org.role_template_id:
                role_service = RoleService(db)
                if role_service.check_user_has_permission(
                    user_id, org_id, resource, action
                ):
                    return  # Permission granted via role

            # Legacy: owners have all permissions
            if user_org.role == "owner":
                return

        # Fall back to direct permission check (ABAC system)
        has_permission = PermissionService.check_permission(
            db,
            user_id,
            resource,
            action
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}"
            )

    return check_permission


def require_owner_role() -> Callable:
    """
    Dependency that requires the user to be an organization owner.

    Checks both new role template system (role_template with name="owner")
    and legacy role field (role="owner").
    """
    async def check_owner(
        auth_context: AuthContext = Depends(get_auth_context),
        db: Session = Depends(get_db)
    ) -> None:
        if not auth_context.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        user_org = db.query(UserOrganization).filter(
            UserOrganization.user_id == auth_context.user.id,
            UserOrganization.organization_id == auth_context.user.organization_id,
        ).first()

        if not user_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner role required"
            )

        # Check new role template system
        if user_org.role_template_id:
            role_service = RoleService(db)
            role = role_service.get_user_role(
                auth_context.user.id,
                auth_context.user.organization_id
            )
            if role and role.role_name == "owner":
                return

        # Check legacy role field
        if user_org.role == "owner":
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required"
        )

    return check_owner

