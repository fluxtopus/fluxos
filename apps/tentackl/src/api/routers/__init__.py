# REVIEW:
# - This export list duplicates router registration in api/app.py and can drift (some routers are missing here).
"""API router modules."""

from .event_bus import router as event_bus_router
from .external_events import router as external_events_router
from .metrics import router as metrics_router
from .monitoring import router as monitoring_router
from .audit import router as audit_router
from .agents import router as agents_router
from .agent_storage import router as agent_storage_router
from .automations import router as automations_router
from .tasks import router as tasks_router
from .inbox import router as inbox_router
from .memories import router as memories_router
from .triggers import router as triggers_router
from .capabilities import router as capabilities_router

__all__ = [
    'event_bus_router',
    'external_events_router',
    'metrics_router',
    'monitoring_router',
    'audit_router',
    'agents_router',
    'agent_storage_router',
    'automations_router',
    'tasks_router',
    'inbox_router',
    'memories_router',
    'triggers_router',
    'capabilities_router',
]
