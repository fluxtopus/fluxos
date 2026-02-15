"""
Permission checking utilities for FastAPI integration.

This module provides reusable components for adding permission checks
to FastAPI routes using the InkPass authorization system.

Example:
    ```python
    from inkpass_sdk import InkPassClient
    from inkpass_sdk.permissions import PermissionChecker

    # Initialize
    client = InkPassClient(config)
    permissions = PermissionChecker(client)

    # Use in routes
    @router.post("/workflows")
    async def create_workflow(
        request: Request,
        _: None = Depends(permissions.require("workflows", "create")),
    ):
        ...
    ```
"""

from typing import Any, Callable

import structlog
from fastapi import Depends, HTTPException, Request, status

logger = structlog.get_logger()


class PermissionChecker:
    """
    Reusable permission checking for FastAPI routes.

    Provides dependency factories that can be used with FastAPI's Depends()
    to enforce permission checks on routes.

    Attributes:
        client: InkPassClient instance for permission checks
        token_header: Header name for authorization (default: "Authorization")
        token_prefix: Token prefix to strip (default: "Bearer ")
    """

    def __init__(
        self,
        client: Any,  # InkPassClient - using Any to avoid circular import
        token_header: str = "Authorization",
        token_prefix: str = "Bearer ",
    ) -> None:
        """
        Initialize PermissionChecker.

        Args:
            client: InkPassClient instance
            token_header: Header name for authorization
            token_prefix: Prefix to strip from token (e.g., "Bearer ")
        """
        self.client = client
        self.token_header = token_header
        self.token_prefix = token_prefix

    def _extract_token(self, request: Request) -> str | None:
        """
        Extract token from request headers.

        Args:
            request: FastAPI request object

        Returns:
            Token string or None if not found
        """
        auth_header = request.headers.get(self.token_header)
        if not auth_header:
            return None

        if auth_header.startswith(self.token_prefix):
            return auth_header[len(self.token_prefix) :]

        return auth_header

    def require(self, resource: str, action: str) -> Callable:
        """
        Create a dependency that requires a specific permission.

        Args:
            resource: Resource name (e.g., "workflows", "notifications")
            action: Action name (e.g., "create", "view", "delete")

        Returns:
            FastAPI dependency function

        Example:
            ```python
            @router.post("/workflows")
            async def create_workflow(
                _: None = Depends(permissions.require("workflows", "create")),
            ):
                ...
            ```
        """

        async def check_permission(request: Request) -> None:
            token = self._extract_token(request)
            if not token:
                logger.warning("Permission check failed - no token", resource=resource, action=action)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            has_permission = await self.client.check_permission(token, resource, action)
            if not has_permission:
                logger.warning(
                    "Permission denied",
                    resource=resource,
                    action=action,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {resource}:{action}",
                )

            logger.debug("Permission granted", resource=resource, action=action)

        return check_permission

    def require_any(self, permissions: list[tuple[str, str]]) -> Callable:
        """
        Create a dependency that requires ANY of the specified permissions.

        User needs at least one of the permissions to access the route.

        Args:
            permissions: List of (resource, action) tuples

        Returns:
            FastAPI dependency function

        Example:
            ```python
            @router.get("/admin-or-owner")
            async def admin_or_owner(
                _: None = Depends(permissions.require_any([
                    ("admin", "access"),
                    ("workflows", "manage"),
                ])),
            ):
                ...
            ```
        """

        async def check_any_permission(request: Request) -> None:
            token = self._extract_token(request)
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            for resource, action in permissions:
                has_permission = await self.client.check_permission(token, resource, action)
                if has_permission:
                    logger.debug("Permission granted (any)", resource=resource, action=action)
                    return

            # None of the permissions matched
            permission_str = ", ".join(f"{r}:{a}" for r, a in permissions)
            logger.warning("Permission denied (require any)", permissions=permission_str)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of [{permission_str}]",
            )

        return check_any_permission

    def require_all(self, permissions: list[tuple[str, str]]) -> Callable:
        """
        Create a dependency that requires ALL of the specified permissions.

        User needs all permissions to access the route.

        Args:
            permissions: List of (resource, action) tuples

        Returns:
            FastAPI dependency function

        Example:
            ```python
            @router.delete("/critical-resource")
            async def delete_critical(
                _: None = Depends(permissions.require_all([
                    ("admin", "access"),
                    ("critical", "delete"),
                ])),
            ):
                ...
            ```
        """

        async def check_all_permissions(request: Request) -> None:
            token = self._extract_token(request)
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            missing = []
            for resource, action in permissions:
                has_permission = await self.client.check_permission(token, resource, action)
                if not has_permission:
                    missing.append(f"{resource}:{action}")

            if missing:
                logger.warning("Permission denied (require all)", missing=missing)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: missing [{', '.join(missing)}]",
                )

            logger.debug("All permissions granted", count=len(permissions))

        return check_all_permissions

    def require_with_context(
        self,
        resource: str,
        action: str,
        context_builder: Callable[[Request], dict[str, Any]],
    ) -> Callable:
        """
        Create a dependency with dynamic ABAC context.

        Allows building context from the request for attribute-based access control.

        Args:
            resource: Resource name
            action: Action name
            context_builder: Function that builds context dict from request

        Returns:
            FastAPI dependency function

        Example:
            ```python
            def build_workflow_context(request: Request) -> dict:
                return {
                    "workflow_id": request.path_params.get("workflow_id"),
                    "owner_id": request.state.user_id,
                }

            @router.patch("/workflows/{workflow_id}")
            async def update_workflow(
                workflow_id: str,
                _: None = Depends(permissions.require_with_context(
                    "workflows",
                    "update",
                    build_workflow_context,
                )),
            ):
                ...
            ```
        """

        async def check_permission_with_context(request: Request) -> None:
            token = self._extract_token(request)
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            context = context_builder(request)
            has_permission = await self.client.check_permission(token, resource, action, context)

            if not has_permission:
                logger.warning(
                    "Permission denied (with context)",
                    resource=resource,
                    action=action,
                    context=context,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {resource}:{action}",
                )

            logger.debug("Permission granted (with context)", resource=resource, action=action)

        return check_permission_with_context


def create_permission_checker(client: Any) -> PermissionChecker:
    """
    Factory function to create a PermissionChecker.

    Args:
        client: InkPassClient instance

    Returns:
        Configured PermissionChecker

    Example:
        ```python
        from inkpass_sdk import InkPassClient
        from inkpass_sdk.permissions import create_permission_checker

        client = InkPassClient(config)
        permissions = create_permission_checker(client)
        ```
    """
    return PermissionChecker(client)
