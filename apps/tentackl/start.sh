#!/bin/bash
# Startup script for Tentackl API Service
# Runs database migrations and starts the API server

set -e

# Configurable worker count (default: 2 for lower idle CPU)
GUNICORN_WORKERS=${GUNICORN_WORKERS:-2}

echo "Starting Tentackl API Service..."

# Parse DATABASE_URL to extract host and port for pg_isready
# Format: postgresql://user:password@host:port/database
if [ -n "$DATABASE_URL" ]; then
    # Extract host and port from DATABASE_URL
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\):.*/\1/p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    DB_USER=$(echo "$DATABASE_URL" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    echo "Parsed DB connection: host=$DB_HOST, port=$DB_PORT, user=$DB_USER"
else
    DB_HOST="${POSTGRES_HOST:-postgres}"
    DB_PORT="${POSTGRES_PORT:-5432}"
    DB_USER="${POSTGRES_USER:-tentackl}"
fi

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
MAX_RETRIES=30
RETRY_COUNT=0
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" 2>/dev/null; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "PostgreSQL failed to become ready after $MAX_RETRIES attempts. Continuing anyway..."
    break
  fi
  echo "PostgreSQL is unavailable (attempt $RETRY_COUNT/$MAX_RETRIES) - sleeping"
  sleep 2
done
echo "PostgreSQL check complete!"

# Wait for Redis to be ready (if REDIS_URL is set)
if [ -n "$REDIS_URL" ]; then
    echo "Waiting for Redis..."
    MAX_RETRIES=15
    RETRY_COUNT=0
    until redis-cli -u "$REDIS_URL" ping > /dev/null 2>&1; do
      RETRY_COUNT=$((RETRY_COUNT + 1))
      if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Redis failed to become ready after $MAX_RETRIES attempts. Continuing anyway..."
        break
      fi
      echo "Redis is unavailable (attempt $RETRY_COUNT/$MAX_RETRIES) - sleeping"
      sleep 2
    done
    echo "Redis check complete!"
else
    echo "REDIS_URL not set, skipping Redis check"
fi

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

echo "Migrations completed successfully!"

# Start the application with gunicorn for production
echo "Starting Tentackl API server on port ${PORT:-8000}..."

if [ "${APP_ENV}" = "production" ]; then
    # Production: Use gunicorn with configurable workers
    echo "Starting with ${GUNICORN_WORKERS} Gunicorn workers..."
    exec gunicorn src.main:app \
        --workers ${GUNICORN_WORKERS} \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:${PORT:-8000} \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --log-level info
else
    # Development: Use uvicorn with reload
    exec uvicorn src.main:app \
        --host 0.0.0.0 \
        --port ${PORT:-8000} \
        --reload
fi
