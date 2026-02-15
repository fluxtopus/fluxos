"""
Permission template system for InkPass.

This module provides code-defined permission templates that are synced to
the database via admin API. Templates define role-based permission sets
for different product types (TENTACKL_SOLO, MIMIC_SOLO, etc.).
"""

from src.templates.role_definitions import (
    ProductType,
    RoleDefinition,
    TemplateDefinition,
)
from src.templates.permission_templates import (
    TEMPLATE_REGISTRY,
    TENTACKL_SOLO_TEMPLATE,
    MIMIC_SOLO_TEMPLATE,
    INKPASS_SOLO_TEMPLATE,
    AIOS_BUNDLE_TEMPLATE,
    get_template_for_product,
)

__all__ = [
    # Enums and classes
    "ProductType",
    "RoleDefinition",
    "TemplateDefinition",
    # Templates
    "TEMPLATE_REGISTRY",
    "TENTACKL_SOLO_TEMPLATE",
    "MIMIC_SOLO_TEMPLATE",
    "INKPASS_SOLO_TEMPLATE",
    "AIOS_BUNDLE_TEMPLATE",
    # Functions
    "get_template_for_product",
]
