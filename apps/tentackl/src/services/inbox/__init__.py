# REVIEW: Importing service classes at module import time can trigger heavy
# REVIEW: dependencies and side effects during startup. Consider lazy imports
# REVIEW: or explicit wiring in application setup.
"""
Inbox services module.

Provides services for the Agent Inbox feature:
- SummaryGenerationService: LLM-powered outcome summaries with fallback
- InboxService: Core inbox operations (list, filter, status, thread, follow-up)
"""

from src.infrastructure.inbox.summary_service import SummaryGenerationService
from src.infrastructure.inbox.inbox_service import InboxService

__all__ = [
    "InboxService",
    "SummaryGenerationService",
]
