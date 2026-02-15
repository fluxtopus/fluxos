"""
Template management module for Tentackl

This module provides template versioning and management capabilities
for the config-based agent generation system.
"""

from src.templates.redis_template_versioning import RedisTemplateVersioning

__all__ = ["RedisTemplateVersioning"]