# REVIEW: Package re-exports calendar helpers at import time; if those helpers
# REVIEW: have heavy dependencies, consider lazy loading to reduce startup cost.
"""Google services package."""

from .calendar_assistant import (
    create_calendar_plan,
)

__all__ = [
    "create_calendar_plan",
]
