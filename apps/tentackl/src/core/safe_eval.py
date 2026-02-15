"""
Safe Expression Evaluator

Replaces Python eval() with simpleeval to prevent remote code execution.
Provides a shared safe_eval() utility that whitelists field access,
comparisons, and boolean logic only.

Security context: The previous eval(expr, {"__builtins__": {}}, locals)
pattern is trivially bypassable via ().__class__.__bases__[0].__subclasses__()
chains. simpleeval restricts to arithmetic, comparisons, and boolean logic.
"""

from typing import Any, Dict, Optional

import structlog
from simpleeval import EvalWithCompoundTypes, InvalidExpression

logger = structlog.get_logger(__name__)

# Safe functions that can be used in expressions
_SAFE_FUNCTIONS = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "sum": sum,
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "type": type,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
}


def safe_eval(
    expression: str,
    names: Optional[Dict[str, Any]] = None,
    functions: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Safely evaluate an expression using simpleeval.

    Supports:
    - Arithmetic: +, -, *, /, //, %, **
    - Comparisons: ==, !=, <, >, <=, >=
    - Boolean logic: and, or, not
    - Containment: in, not in
    - Attribute/index access: x.field, x['key'], x[0]
    - List comprehensions: [x for x in items if x > 0]
    - Ternary: x if condition else y
    - String operations on values
    - Safe built-in functions (len, str, int, etc.)

    Does NOT support:
    - Import statements
    - Function definitions
    - Class definitions
    - __dunder__ attribute access
    - Arbitrary code execution

    Args:
        expression: The expression string to evaluate.
        names: Dictionary of variable names available in the expression.
        functions: Additional functions to make available (merged with defaults).

    Returns:
        The result of evaluating the expression.

    Raises:
        InvalidExpression: If the expression uses disallowed operations.
        Exception: For evaluation errors (NameError, TypeError, etc.).
    """
    evaluator = EvalWithCompoundTypes()

    # Set available names/variables
    if names:
        evaluator.names = names

    # Merge default safe functions with any custom ones
    merged_functions = dict(_SAFE_FUNCTIONS)
    if functions:
        merged_functions.update(functions)
    evaluator.functions = merged_functions

    return evaluator.eval(expression)


def safe_eval_condition(
    condition: str,
    context: Optional[Dict[str, Any]] = None,
    default: bool = False,
) -> bool:
    """
    Safely evaluate a boolean condition expression.

    This is a convenience wrapper around safe_eval() that:
    - Always returns a bool
    - Returns a configurable default on error instead of raising
    - Logs evaluation failures as warnings

    Args:
        condition: The condition expression to evaluate.
        context: Dictionary of variable names available in the expression.
        default: Value to return if evaluation fails.

    Returns:
        Boolean result of the condition, or default on error.
    """
    try:
        result = safe_eval(condition, names=context or {})
        return bool(result)
    except Exception as e:
        logger.warning(
            "Safe condition evaluation failed",
            condition=condition,
            error=str(e),
        )
        return default
