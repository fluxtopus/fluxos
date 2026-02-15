"""
Permission template definitions for all product types.

This is the source of truth for permission templates. Templates defined here
are synced to the database via the admin API.

To update permissions:
1. Modify the template definitions below
2. Increment the version number
3. Call POST /api/v1/admin/templates/sync to sync to DB
4. Call POST /api/v1/admin/templates/{id}/propagate to propagate to orgs
"""

from typing import Optional, Set

from src.templates.role_definitions import (
    Permission,
    ProductType,
    RoleDefinition,
    TemplateDefinition,
)


# =============================================================================
# PERMISSION SETS BY SERVICE
# =============================================================================

# InkPass core permissions (shared by all products)
INKPASS_CORE_PERMISSIONS: Set[Permission] = {
    ("organization", "view"),
    ("organization", "manage"),
    ("users", "view"),
    ("users", "create"),
    ("users", "manage"),
    ("users", "delete"),
    ("groups", "view"),
    ("groups", "create"),
    ("groups", "manage"),
    ("groups", "delete"),
    ("permissions", "view"),
    ("permissions", "create"),
    ("permissions", "manage"),
    ("permissions", "delete"),
    ("permissions", "assign"),
    ("api_keys", "view"),
    ("api_keys", "create"),
    ("api_keys", "manage"),
    ("api_keys", "delete"),
    ("billing", "view"),
    ("billing", "create"),
    ("billing", "manage"),
    ("files", "view"),
    ("files", "create"),
    ("files", "manage"),
    ("files", "delete"),
    ("plans", "view"),
    ("plans", "create"),
    ("plans", "manage"),
}

# Tentackl service permissions
TENTACKL_PERMISSIONS: Set[Permission] = {
    ("workflows", "view"),
    ("workflows", "create"),
    ("workflows", "update"),
    ("workflows", "execute"),
    ("workflows", "delete"),
    ("workflows", "control"),
    ("workflow_specs", "view"),
    ("workflow_specs", "create"),
    ("workflow_specs", "update"),
    ("workflow_specs", "delete"),
    ("workflow_specs", "share"),
    ("workflow_runs", "view"),
    ("workflow_runs", "execute"),
    ("agents", "view"),
    ("agents", "create"),
    ("agents", "update"),
    ("agents", "delete"),
    ("agents", "execute"),
    ("agents", "search"),
    # Capabilities management (system agents, primitives, plugins) - admin only
    ("capabilities", "view"),
    ("capabilities", "manage"),
    ("tasks", "view"),
    ("tasks", "create"),
    ("tasks", "update"),
    ("tasks", "delete"),
    ("tasks", "execute"),
    ("tasks", "assign"),
    ("checkpoints", "view"),
    ("checkpoints", "resolve"),
    ("preferences", "view"),
    ("preferences", "create"),
    ("preferences", "delete"),
    ("events", "view"),
    ("events", "publish"),
    ("events", "subscribe"),
    ("webhooks", "view"),
    ("webhooks", "create"),
    ("webhooks", "delete"),
    ("workspace", "view"),
    ("workspace", "create"),
    ("workspace", "update"),
    ("workspace", "delete"),
    ("workspace", "query"),
    ("workspace_types", "view"),
    ("workspace_types", "create"),
    ("audit", "view"),
    ("metrics", "view"),
    ("metrics", "admin"),
    # Integration system (proxied from Mimic)
    ("integrations", "view"),
    ("integrations", "create"),
    ("integrations", "update"),
    ("integrations", "delete"),
    ("integrations", "execute"),
}

# Mimic service permissions
MIMIC_PERMISSIONS: Set[Permission] = {
    ("notifications", "send"),
    ("notifications", "view"),
    ("templates", "view"),
    ("templates", "create"),
    ("templates", "update"),
    ("templates", "delete"),
    ("workflows", "view"),
    ("workflows", "create"),
    ("workflows", "update"),
    ("workflows", "delete"),
    ("workflows", "trigger"),
    ("provider_keys", "view"),
    ("provider_keys", "create"),
    ("provider_keys", "update"),
    ("provider_keys", "delete"),
    ("provider_keys", "test"),
    ("delivery_logs", "view"),
    ("analytics", "view"),
    ("webhooks", "configure"),
    ("webhooks", "view"),
    ("gateway", "view"),
    ("gateway", "admin"),
    # Integration system (INT-001 to INT-021)
    ("integrations", "view"),
    ("integrations", "create"),
    ("integrations", "update"),
    ("integrations", "delete"),
}

# Platform service permissions (admin/platform)
AIOS_PERMISSIONS: Set[Permission] = {
    ("jobs", "view"),
    ("jobs", "update"),
    ("jobs", "delete"),
    ("jobs", "retry"),
    ("jobs", "cancel"),
    ("customers", "view"),
    ("customers", "create"),
    ("customers", "update"),
    ("customers", "delete"),
    ("credits", "view"),
    ("credits", "create"),
    ("credits", "spend"),
    ("cells", "view"),
    ("cells", "create"),
    ("cells", "manage"),
    ("cells", "delete"),
    ("cells", "provision"),
    ("cells", "restart"),
    ("usage", "view"),
    ("usage", "admin"),
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

# Billing permissions (owner-only)
BILLING_PERMISSIONS: Set[Permission] = {
    ("billing", "view"),
    ("billing", "create"),
    ("billing", "manage"),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _filter_by_actions(permissions: Set[Permission], actions: Set[str]) -> Set[Permission]:
    """Filter permissions to only include specified actions."""
    return {p for p in permissions if p[1] in actions}


def _get_view_permissions(permissions: Set[Permission]) -> Set[Permission]:
    """Get only view/query/search permissions."""
    return _filter_by_actions(permissions, {"view", "query", "search"})


def _get_developer_permissions(permissions: Set[Permission]) -> Set[Permission]:
    """Get permissions suitable for developers (view, create, execute, etc.)."""
    return _filter_by_actions(
        permissions,
        {"view", "create", "update", "execute", "trigger", "query", "search", "send", "resolve"}
    )


def _get_admin_permissions(permissions: Set[Permission]) -> Set[Permission]:
    """Get permissions for admins (everything except billing manage)."""
    return permissions - {("billing", "manage")}


# =============================================================================
# INKPASS SOLO TEMPLATE
# =============================================================================

INKPASS_SOLO_TEMPLATE = TemplateDefinition(
    name="INKPASS_SOLO",
    product_type=ProductType.INKPASS_SOLO,
    version=1,
    description="InkPass standalone product for authentication and authorization",
    roles=[
        RoleDefinition(
            name="owner",
            display_name="Owner",
            description="Full access to all InkPass features including billing",
            permissions=INKPASS_CORE_PERMISSIONS,
            priority=100,
        ),
        RoleDefinition(
            name="admin",
            display_name="Administrator",
            description="Full access except billing management",
            permissions=_get_admin_permissions(INKPASS_CORE_PERMISSIONS),
            priority=80,
            inherits_from="developer",
        ),
        RoleDefinition(
            name="developer",
            display_name="Developer",
            description="Can create and manage resources, but cannot delete org-level items",
            permissions=_get_developer_permissions(INKPASS_CORE_PERMISSIONS),
            priority=50,
            inherits_from="viewer",
        ),
        RoleDefinition(
            name="viewer",
            display_name="Viewer",
            description="Read-only access to all resources",
            permissions=_get_view_permissions(INKPASS_CORE_PERMISSIONS),
            priority=10,
        ),
    ],
)


# =============================================================================
# TENTACKL SOLO TEMPLATE
# =============================================================================

_TENTACKL_ALL = TENTACKL_PERMISSIONS | INKPASS_CORE_PERMISSIONS

TENTACKL_SOLO_TEMPLATE = TemplateDefinition(
    name="TENTACKL_SOLO",
    product_type=ProductType.TENTACKL_SOLO,
    version=3,  # Bumped for capabilities permissions
    description="Tentackl standalone product for workflow orchestration",
    roles=[
        RoleDefinition(
            name="owner",
            display_name="Owner",
            description="Full access to all Tentackl features including billing",
            permissions=_TENTACKL_ALL,
            priority=100,
        ),
        RoleDefinition(
            name="admin",
            display_name="Administrator",
            description="Full access except billing management",
            permissions=_get_admin_permissions(_TENTACKL_ALL),
            priority=80,
            inherits_from="developer",
        ),
        RoleDefinition(
            name="developer",
            display_name="Developer",
            description="Can create and execute workflows, agents, and tasks",
            permissions=_get_developer_permissions(_TENTACKL_ALL),
            priority=50,
            inherits_from="viewer",
        ),
        RoleDefinition(
            name="viewer",
            display_name="Viewer",
            description="Read-only access to workflows and resources",
            permissions=_get_view_permissions(_TENTACKL_ALL),
            priority=10,
        ),
    ],
)


# =============================================================================
# MIMIC SOLO TEMPLATE
# =============================================================================

_MIMIC_ALL = MIMIC_PERMISSIONS | INKPASS_CORE_PERMISSIONS

MIMIC_SOLO_TEMPLATE = TemplateDefinition(
    name="MIMIC_SOLO",
    product_type=ProductType.MIMIC_SOLO,
    version=2,  # Bumped for integrations permissions
    description="Mimic standalone product for notification workflows",
    roles=[
        RoleDefinition(
            name="owner",
            display_name="Owner",
            description="Full access to all Mimic features including billing",
            permissions=_MIMIC_ALL,
            priority=100,
        ),
        RoleDefinition(
            name="admin",
            display_name="Administrator",
            description="Full access except billing management",
            permissions=_get_admin_permissions(_MIMIC_ALL),
            priority=80,
            inherits_from="developer",
        ),
        RoleDefinition(
            name="developer",
            display_name="Developer",
            description="Can create templates, send notifications, and manage workflows",
            permissions=_get_developer_permissions(_MIMIC_ALL),
            priority=50,
            inherits_from="viewer",
        ),
        RoleDefinition(
            name="viewer",
            display_name="Viewer",
            description="Read-only access to templates and delivery logs",
            permissions=_get_view_permissions(_MIMIC_ALL),
            priority=10,
        ),
    ],
)


# =============================================================================
# AIOS BUNDLE TEMPLATE
# =============================================================================

_AIOS_ALL = (
    TENTACKL_PERMISSIONS |
    MIMIC_PERMISSIONS |
    AIOS_PERMISSIONS |
    INKPASS_CORE_PERMISSIONS
)

AIOS_BUNDLE_TEMPLATE = TemplateDefinition(
    name="AIOS_BUNDLE",
    product_type=ProductType.AIOS_BUNDLE,
    version=4,  # Bumped for capabilities permissions
    description="Full platform with all services",
    roles=[
        RoleDefinition(
            name="owner",
            display_name="Owner",
            description="Full access to all platform features",
            permissions=_AIOS_ALL,
            priority=100,
        ),
        RoleDefinition(
            name="admin",
            display_name="Administrator",
            description="Full access except billing management and platform admin",
            permissions=_get_admin_permissions(_AIOS_ALL) - {("usage", "admin"), ("marketplace", "admin")},
            priority=80,
            inherits_from="developer",
        ),
        RoleDefinition(
            name="developer",
            display_name="Developer",
            description="Can use all services but cannot manage org-level settings",
            permissions=_get_developer_permissions(_AIOS_ALL),
            priority=50,
            inherits_from="viewer",
        ),
        RoleDefinition(
            name="viewer",
            display_name="Viewer",
            description="Read-only access across all services",
            permissions=_get_view_permissions(_AIOS_ALL),
            priority=10,
        ),
    ],
)


# =============================================================================
# TEMPLATE REGISTRY
# =============================================================================

TEMPLATE_REGISTRY: dict[ProductType, TemplateDefinition] = {
    ProductType.INKPASS_SOLO: INKPASS_SOLO_TEMPLATE,
    ProductType.TENTACKL_SOLO: TENTACKL_SOLO_TEMPLATE,
    ProductType.MIMIC_SOLO: MIMIC_SOLO_TEMPLATE,
    ProductType.AIOS_BUNDLE: AIOS_BUNDLE_TEMPLATE,
}


def get_template_for_product(product_type: ProductType) -> Optional[TemplateDefinition]:
    """
    Get the template definition for a product type.

    Args:
        product_type: The product type to get the template for

    Returns:
        TemplateDefinition if found, None otherwise
    """
    return TEMPLATE_REGISTRY.get(product_type)


def get_template_by_name(name: str) -> Optional[TemplateDefinition]:
    """
    Get a template by name.

    Args:
        name: Template name (e.g., "TENTACKL_SOLO")

    Returns:
        TemplateDefinition if found, None otherwise
    """
    for template in TEMPLATE_REGISTRY.values():
        if template.name == name:
            return template
    return None


def get_all_templates() -> list[TemplateDefinition]:
    """Get all template definitions."""
    return list(TEMPLATE_REGISTRY.values())
