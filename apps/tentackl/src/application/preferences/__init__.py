"""Application use cases for preferences."""

from src.application.preferences.use_cases import (
    PreferenceForbidden,
    PreferenceNotFound,
    PreferenceUseCases,
    PreferenceValidationError,
)

__all__ = [
    "PreferenceUseCases",
    "PreferenceNotFound",
    "PreferenceForbidden",
    "PreferenceValidationError",
]
