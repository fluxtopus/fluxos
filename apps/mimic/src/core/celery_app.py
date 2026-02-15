"""Celery application for Mimic webhook gateway."""

from celery import Celery
from src.config import settings

# Create Celery app
app = Celery(
    'mimic',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['src.core.tasks']
)

# Configure Celery
# Use a dedicated queue to avoid task stealing by other services (e.g. Tentackl)
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
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=290,
    task_default_queue='mimic',
)
