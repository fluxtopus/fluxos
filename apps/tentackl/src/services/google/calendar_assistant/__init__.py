# REVIEW: This module simply re-exports helpers; consider documenting ownership
# REVIEW: and expected inputs/outputs in a dedicated service class to clarify
# REVIEW: boundaries with workflow planning.
"""
Calendar Assistant Service

Automated calendar management from email analysis.
"""

from .calendar_plan_factory import create_calendar_plan

__all__ = [
    "create_calendar_plan",
]
