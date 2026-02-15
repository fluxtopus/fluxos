"""
Primitive Registry

Manages registration and execution of primitive operations.
Primitives are deterministic, no-LLM operations that can be composed.

Handler functions must be async and follow this signature:
    async def handler(inputs: Dict[str, Any]) -> Dict[str, Any]
"""

import structlog
from typing import Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass
from datetime import datetime

logger = structlog.get_logger(__name__)

# Type for primitive handlers
PrimitiveHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class PrimitiveResult:
    """Result from a primitive execution."""
    status: str  # "success" or "error"
    output: Any
    execution_time_ms: int
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
        }


class PrimitiveRegistry:
    """
    Registry for primitive handlers.

    Primitives are registered by name (e.g., "http.get", "json.parse")
    and can be executed without LLM involvement.
    """

    _handlers: Dict[str, PrimitiveHandler] = {}

    @classmethod
    def register(cls, name: str, handler: PrimitiveHandler) -> None:
        """Register a primitive handler."""
        cls._handlers[name] = handler
        logger.debug("Registered primitive", name=name)

    @classmethod
    def get(cls, name: str) -> Optional[PrimitiveHandler]:
        """Get a primitive handler by name."""
        return cls._handlers.get(name)

    @classmethod
    def list_all(cls) -> list:
        """List all registered primitive names."""
        return list(cls._handlers.keys())

    @classmethod
    async def execute(cls, name: str, inputs: Dict[str, Any]) -> PrimitiveResult:
        """
        Execute a primitive by name.

        Args:
            name: Primitive name (e.g., "http.get")
            inputs: Input parameters for the primitive

        Returns:
            PrimitiveResult with output or error
        """
        start_time = datetime.utcnow()

        handler = cls.get(name)
        if not handler:
            return PrimitiveResult(
                status="error",
                output=None,
                execution_time_ms=0,
                error=f"Unknown primitive: {name}",
            )

        try:
            output = await handler(inputs)
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return PrimitiveResult(
                status="success",
                output=output,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            logger.error("Primitive execution failed", name=name, error=str(e))

            return PrimitiveResult(
                status="error",
                output=None,
                execution_time_ms=execution_time,
                error=str(e),
            )


# Convenience functions
async def execute_primitive(name: str, inputs: Dict[str, Any]) -> PrimitiveResult:
    """Execute a primitive by name."""
    return await PrimitiveRegistry.execute(name, inputs)


def get_primitive_handler(name: str) -> Optional[PrimitiveHandler]:
    """Get a primitive handler by name."""
    return PrimitiveRegistry.get(name)


# Auto-register handlers on import
def _register_all_handlers():
    """Register all primitive handlers from handler modules."""
    from src.primitives import http, json_ops, list_ops, string_ops

    # HTTP primitives
    PrimitiveRegistry.register("http.get", http.http_get)
    PrimitiveRegistry.register("http.post", http.http_post)

    # JSON primitives
    PrimitiveRegistry.register("json.parse", json_ops.json_parse)
    PrimitiveRegistry.register("json.stringify", json_ops.json_stringify)

    # List primitives
    PrimitiveRegistry.register("list.filter", list_ops.list_filter)
    PrimitiveRegistry.register("list.map", list_ops.list_map)
    PrimitiveRegistry.register("list.reduce", list_ops.list_reduce)

    # String primitives
    PrimitiveRegistry.register("string.template", string_ops.string_template)
    PrimitiveRegistry.register("string.split", string_ops.string_split)
    PrimitiveRegistry.register("string.replace", string_ops.string_replace)
    PrimitiveRegistry.register("string.match", string_ops.string_match)

    logger.info("Registered all primitives", count=len(PrimitiveRegistry._handlers))


# Register handlers when module is imported
try:
    _register_all_handlers()
except ImportError as e:
    logger.warning("Could not auto-register primitives", error=str(e))
