"""Infrastructure adapter for capability validation helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from src.infrastructure.capabilities.capability_yaml_validation import (
    extract_keywords as _extract_keywords,
    get_validation_service as _get_validation_service,
)


def extract_keywords(spec: Dict[str, Any]) -> List[str]:
    """Extract normalized keywords from a capability spec."""
    return _extract_keywords(spec)


def get_validation_service():
    """Resolve the shared capability YAML validation service."""
    return _get_validation_service()
