# REVIEW:
# - Beat schedule is hard-coded in code; operational changes require deploys.
from celery import Celery
from src.core.config import settings

# Create Celery app
app = Celery(
    'tentackl',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['src.core.tasks']
)

# Configure Celery
# Use a dedicated queue to avoid task stealing by other services (e.g. Mimic)
# sharing the same Redis broker.
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=settings.AGENT_DEFAULT_TIMEOUT,
    task_soft_time_limit=settings.AGENT_DEFAULT_TIMEOUT - 10,
    task_default_queue='tentackl',
)

# Beat schedule for periodic tasks
# Note: Workflow schedules are stored in the database and checked by the
# check-scheduled-workflows task below. This approach works across containers
# because the periodic task is hardcoded here (so Celery Beat knows about it),
# and the actual schedule data comes from the database (which both processes can access).
#
# Frequencies optimized for lower idle CPU while maintaining acceptable responsiveness:
# - Cleanup: 10 min (not urgent, can be delayed)
# - Heartbeat: 2 min (agents can tolerate brief delays)
# - Scheduled automations: 2 min (most schedules are hourly/daily anyway)
app.conf.beat_schedule = {
    'cleanup-expired-agents': {
        'task': 'src.core.tasks.cleanup_expired_agents',
        'schedule': 600.0,  # Every 10 minutes (was 5 min)
    },
    'heartbeat-check': {
        'task': 'src.core.tasks.check_agent_heartbeats',
        'schedule': 120.0,  # Every 2 minutes (was 30 sec)
    },
    # DEPRECATED: check-scheduled-workflows and calendar-assistant-poll removed
    # Scheduling is driven exclusively by the automations table.
    'check-automations': {
        'task': 'src.core.tasks.check_automations',
        'schedule': 120.0,  # Every 2 minutes
    },
    'retry-failed-memory-embeddings': {
        'task': 'src.core.tasks.retry_failed_memory_embeddings',
        'schedule': 600.0,  # Every 10 minutes
    },
}
