"""
Core exceptions for the Tentackl system.
"""


class TentacklException(Exception):
    """Base exception for all Tentackl errors"""
    pass


class AgentExecutionError(TentacklException):
    """Error during agent execution"""
    pass


class ValidationError(TentacklException):
    """Validation error"""
    pass


class ConfigurationError(TentacklException):
    """Configuration error"""
    pass


# Capability-related exceptions
class CapabilityError(TentacklException):
    """Base capability error"""
    pass


class CapabilityNotFoundError(CapabilityError):
    """Capability not found in registry"""
    pass


class CapabilityBindingError(CapabilityError):
    """Error binding capability to agent"""
    pass


# LLM-related exceptions
class LLMError(TentacklException):
    """LLM operation error"""
    pass


class PromptError(LLMError):
    """Prompt-related error"""
    pass


# State-related exceptions
class StateError(TentacklException):
    """State management error"""
    pass


class BudgetError(TentacklException):
    """Budget-related error"""
    pass
