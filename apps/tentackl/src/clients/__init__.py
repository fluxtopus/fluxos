"""Client modules for external services."""

try:
    from .inkpass import inkpass_client

    __all__ = ["inkpass_client"]
except ImportError:
    # InkPass SDK not installed — standalone mode
    inkpass_client = None  # type: ignore[assignment]
    __all__ = []
