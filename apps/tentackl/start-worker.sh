#!/bin/bash
# Startup script for Tentackl Celery Worker
# Handles async agent tasks

set -e

# Configurable concurrency (default: 2 for lower idle CPU)
CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-2}

echo "Starting Tentackl Celery Worker..."

# Wait for Redis to be ready
echo "Waiting for Redis..."
until redis-cli -u "${CELERY_BROKER_URL:-redis://redis:6379/1}" ping > /dev/null 2>&1; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done
echo "Redis is ready!"

# Start Celery worker
echo "Starting Celery worker with concurrency=${CELERY_CONCURRENCY}..."
exec celery -A src.core.celery_app worker \
    --loglevel=info \
    --concurrency=${CELERY_CONCURRENCY} \
    --max-tasks-per-child=1000 \
    -Q tentackl
