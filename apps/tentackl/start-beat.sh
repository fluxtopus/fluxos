#!/bin/bash
# Startup script for Tentackl Celery Beat
# Handles scheduled workflow tasks

set -e

echo "Starting Tentackl Celery Beat..."

# Wait for Redis to be ready
echo "Waiting for Redis..."
until redis-cli -u "${CELERY_BROKER_URL:-redis://redis:6379/1}" ping > /dev/null 2>&1; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done
echo "Redis is ready!"

# Start Celery beat
echo "Starting Celery beat scheduler..."
exec celery -A src.core.celery_app beat \
    --loglevel=info
