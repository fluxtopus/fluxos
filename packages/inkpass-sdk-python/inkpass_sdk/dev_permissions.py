"""
Development permission presets and definitions.

This module contains permission definitions and role presets for development.

Usage:
    ```python
    from inkpass_sdk.dev_permissions import (
        ALL_PERMISSIONS,
        ROLE_PRESETS,
        TENTACKL_PERMISSIONS,
        get_permissions_for_preset,
    )

    # Get all permissions for admin preset
    admin_perms = get_permissions_for_preset("admin")

    # Get only Tentackl permissions
    tentackl_perms = TENTACKL_PERMISSIONS
    ```
"""

from typing import Set, Tuple

# Type alias for permission tuple (resource, action)
Permission = Tuple[str, str]


# =============================================================================
# TENTACKL SERVICE PERMISSIONS
# =============================================================================

TENTACKL_RESOURCES = {
    "workflows",
    "workflow_specs",
    "workflow_runs",
    "agents",
    "tasks",
    "checkpoints",
    "preferences",
    "events",
    "webhooks",
    "workspace",
    "workspace_types",
    "audit",
    "metrics",
}

TENTACKL_PERMISSIONS: Set[Permission] = {
    # Workflows - Core workflow management
    ("workflows", "view"),
    ("workflows", "create"),
    ("workflows", "update"),
    ("workflows", "execute"),
    ("workflows", "delete"),
    ("workflows", "control"),  # pause/resume/signal
    # Workflow Specs - Workflow templates
    ("workflow_specs", "view"),
    ("workflow_specs", "create"),
    ("workflow_specs", "update"),
    ("workflow_specs", "delete"),
    ("workflow_specs", "share"),  # Make public
    # Workflow Runs - Execution instances
    ("workflow_runs", "view"),
    ("workflow_runs", "execute"),
    # Agents - Agent registry and operations
    ("agents", "view"),
    ("agents", "create"),
    ("agents", "update"),
    ("agents", "delete"),
    ("agents", "execute"),
    ("agents", "search"),
    # Tasks - Task management
    ("tasks", "view"),
    ("tasks", "create"),
    ("tasks", "update"),
    ("tasks", "delete"),
    ("tasks", "execute"),
    ("tasks", "assign"),
    # Checkpoints - Checkpoint system
    ("checkpoints", "view"),
    ("checkpoints", "resolve"),
    # Preferences - User preferences
    ("preferences", "view"),
    ("preferences", "create"),
    ("preferences", "delete"),
    # Events - Event bus
    ("events", "view"),
    ("events", "publish"),
    ("events", "subscribe"),
    # Webhooks - External webhooks
    ("webhooks", "view"),
    ("webhooks", "create"),
    ("webhooks", "delete"),
    # Workspace - Workspace objects
    ("workspace", "view"),
    ("workspace", "create"),
    ("workspace", "update"),
    ("workspace", "delete"),
    ("workspace", "query"),
    # Workspace Types - Type schemas
    ("workspace_types", "view"),
    ("workspace_types", "create"),
    # Audit - Audit logs
    ("audit", "view"),
    # Metrics - Performance metrics
    ("metrics", "view"),
    ("metrics", "admin"),
}


# =============================================================================
# MIMIC SERVICE PERMISSIONS
# =============================================================================

MIMIC_RESOURCES = {
    "notifications",
    "templates",
    "workflows",  # Mimic notification workflows (separate from Tentackl)
    "provider_keys",
    "delivery_logs",
    "analytics",
    "webhooks",  # Mimic webhook callbacks (separate from Tentackl)
    "gateway",
}

MIMIC_PERMISSIONS: Set[Permission] = {
    # Notifications - Send and track
    ("notifications", "send"),
    ("notifications", "view"),
    # Templates - Notification templates
    ("templates", "view"),
    ("templates", "create"),
    ("templates", "update"),
    ("templates", "delete"),
    # Workflows - Automation workflows (Mimic notification workflows)
    ("workflows", "view"),
    ("workflows", "create"),
    ("workflows", "update"),
    ("workflows", "delete"),
    ("workflows", "trigger"),
    # Provider Keys - BYOK credentials
    ("provider_keys", "view"),
    ("provider_keys", "create"),
    ("provider_keys", "update"),
    ("provider_keys", "delete"),
    ("provider_keys", "test"),
    # Delivery Logs - Tracking
    ("delivery_logs", "view"),
    # Analytics - Usage analytics
    ("analytics", "view"),
    # Webhooks - Callback configuration
    ("webhooks", "configure"),
    ("webhooks", "view"),
    # Gateway - Admin webhook monitoring
    ("gateway", "view"),
    ("gateway", "admin"),
}


# =============================================================================
# AIOS PLATFORM PERMISSIONS
# =============================================================================

AIOS_RESOURCES = {
    "jobs",
    "customers",
    "credits",
    "cells",
    "usage",
    "marketplace",
}

AIOS_PERMISSIONS: Set[Permission] = {
    # Jobs - Provisioning jobs
    ("jobs", "view"),
    ("jobs", "update"),
    ("jobs", "delete"),
    ("jobs", "retry"),
    ("jobs", "cancel"),
    # Customers - Customer management
    ("customers", "view"),
    ("customers", "create"),
    ("customers", "update"),
    ("customers", "delete"),
    # Credits - Credit management
    ("credits", "view"),
    ("credits", "create"),
    ("credits", "spend"),
    # Cells - Cell infrastructure
    ("cells", "view"),
    ("cells", "create"),
    ("cells", "manage"),
    ("cells", "delete"),
    ("cells", "provision"),
    ("cells", "restart"),
    # Usage - Usage metrics & billing
    ("usage", "view"),
    ("usage", "admin"),
    # Marketplace - Marketplace operations
    ("marketplace", "view"),
    ("marketplace", "create"),
    ("marketplace", "update"),
    ("marketplace", "delete"),
    ("marketplace", "publish"),
    ("marketplace", "purchase"),
    ("marketplace", "download"),
    ("marketplace", "review"),
    ("marketplace", "admin"),
}


# =============================================================================
# INKPASS CORE PERMISSIONS (already exist in production)
# =============================================================================

INKPASS_RESOURCES = {
    "organization",
    "users",
    "groups",
    "permissions",
    "api_keys",
    "billing",
    "files",
    "plans",
}

INKPASS_PERMISSIONS: Set[Permission] = {
    # Organization
    ("organization", "view"),
    ("organization", "manage"),
    # Users
    ("users", "view"),
    ("users", "create"),
    ("users", "manage"),
    ("users", "delete"),
    # Groups
    ("groups", "view"),
    ("groups", "create"),
    ("groups", "manage"),
    ("groups", "delete"),
    # Permissions
    ("permissions", "view"),
    ("permissions", "create"),
    ("permissions", "manage"),
    ("permissions", "delete"),
    ("permissions", "assign"),
    # API Keys
    ("api_keys", "view"),
    ("api_keys", "create"),
    ("api_keys", "manage"),
    ("api_keys", "delete"),
    # Billing
    ("billing", "view"),
    ("billing", "create"),
    ("billing", "manage"),
    # Files
    ("files", "view"),
    ("files", "create"),
    ("files", "manage"),
    ("files", "delete"),
    # Plans
    ("plans", "view"),
    ("plans", "create"),
    ("plans", "manage"),
}


# =============================================================================
# COMBINED PERMISSIONS
# =============================================================================

ALL_PERMISSIONS: Set[Permission] = (
    TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS | INKPASS_PERMISSIONS
)

# Service-specific combined sets (excluding InkPass core which all services need)
SERVICE_PERMISSIONS = {
    "tentackl": TENTACKL_PERMISSIONS | INKPASS_PERMISSIONS,
    "mimic": MIMIC_PERMISSIONS | INKPASS_PERMISSIONS,
    "aios": AIOS_PERMISSIONS | INKPASS_PERMISSIONS,
    "inkpass": INKPASS_PERMISSIONS,
}


# =============================================================================
# ROLE PRESETS
# =============================================================================

def _filter_by_actions(permissions: Set[Permission], actions: Set[str]) -> Set[Permission]:
    """Filter permissions to only include specified actions."""
    return {p for p in permissions if p[1] in actions}


ROLE_PRESETS: dict[str, Set[Permission]] = {
    # Full admin access to everything
    "admin": ALL_PERMISSIONS,
    # Service-specific admin roles
    "tentackl_admin": TENTACKL_PERMISSIONS | INKPASS_PERMISSIONS,
    "mimic_admin": MIMIC_PERMISSIONS | INKPASS_PERMISSIONS,
    "aios_admin": AIOS_PERMISSIONS | INKPASS_PERMISSIONS,
    # Developer - can view, create, execute but not delete or admin
    "developer": _filter_by_actions(
        ALL_PERMISSIONS,
        {"view", "create", "update", "execute", "trigger", "query", "search", "send"},
    ),
    # Operator - can view and execute, but not create or modify
    "operator": _filter_by_actions(
        ALL_PERMISSIONS,
        {"view", "execute", "trigger", "query", "search", "send", "resolve"},
    ),
    # Viewer - read-only access
    "viewer": _filter_by_actions(ALL_PERMISSIONS, {"view", "query", "search"}),
    # Workflow operator - specific to workflow execution
    "workflow_operator": {
        ("workflows", "view"),
        ("workflows", "execute"),
        ("workflow_specs", "view"),
        ("workflow_runs", "view"),
        ("workflow_runs", "execute"),
        ("agents", "view"),
        ("agents", "execute"),
        ("tasks", "view"),
        ("tasks", "execute"),
        ("checkpoints", "view"),
        ("checkpoints", "resolve"),
    },
    # Notification sender - can send notifications
    "notification_sender": {
        ("notifications", "send"),
        ("notifications", "view"),
        ("templates", "view"),
        ("delivery_logs", "view"),
    },
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_permissions_for_preset(preset: str) -> Set[Permission]:
    """
    Get permissions for a named preset.

    Args:
        preset: Preset name (e.g., "admin", "developer", "viewer")

    Returns:
        Set of (resource, action) tuples

    Raises:
        ValueError: If preset is not found
    """
    if preset not in ROLE_PRESETS:
        available = ", ".join(sorted(ROLE_PRESETS.keys()))
        raise ValueError(f"Unknown preset '{preset}'. Available: {available}")
    return ROLE_PRESETS[preset]


def get_permissions_for_service(service: str) -> Set[Permission]:
    """
    Get all permissions for a specific service.

    Args:
        service: Service name ("tentackl", "mimic", "aios", "inkpass")

    Returns:
        Set of (resource, action) tuples

    Raises:
        ValueError: If service is not found
    """
    if service not in SERVICE_PERMISSIONS:
        available = ", ".join(sorted(SERVICE_PERMISSIONS.keys()))
        raise ValueError(f"Unknown service '{service}'. Available: {available}")
    return SERVICE_PERMISSIONS[service]


def format_permissions_for_api(permissions: Set[Permission]) -> list[dict[str, str]]:
    """
    Format permissions for API creation calls.

    Args:
        permissions: Set of (resource, action) tuples

    Returns:
        List of dicts with "resource" and "action" keys
    """
    return [{"resource": r, "action": a} for r, a in sorted(permissions)]


def get_new_permissions() -> Set[Permission]:
    """
    Get permissions that need to be created (excluding InkPass core which already exists).

    Returns:
        Set of (resource, action) tuples for Tentackl and Mimic
    """
    return TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS


# =============================================================================
# PERMISSION COUNTS (for reference)
# =============================================================================

PERMISSION_COUNTS = {
    "tentackl": len(TENTACKL_PERMISSIONS),
    "mimic": len(MIMIC_PERMISSIONS),
    "aios": len(AIOS_PERMISSIONS),
    "inkpass": len(INKPASS_PERMISSIONS),
    "total_new": len(get_new_permissions()),
    "total_all": len(ALL_PERMISSIONS),
}
