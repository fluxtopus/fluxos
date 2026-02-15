"""
Contract Enforcement System

Validates inputs and outputs against schemas to ensure
bad data doesn't propagate between steps.
"""

from src.contracts.validator import (
    ContractValidator,
    ValidationResult,
    ValidationError,
    validate_inputs,
    validate_outputs,
)

__all__ = [
    "ContractValidator",
    "ValidationResult",
    "ValidationError",
    "validate_inputs",
    "validate_outputs",
]
