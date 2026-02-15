#!/bin/bash
# Startup script for Mimic API Service
# Sets up Alembic (if needed), runs migrations, and starts the API server

set -e

echo "Starting Mimic API Service..."

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
    DB_USER="${POSTGRES_USER:-mimic}"
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

# Check if alembic is initialized
if [ ! -d "alembic" ]; then
    echo "Alembic not initialized. Setting up..."
    alembic init alembic
    echo "Alembic initialized. Please configure alembic.ini and env.py before deployment."
fi

# Run database migrations
echo "Running database migrations..."
if [ -d "alembic/versions" ] && [ "$(ls -A alembic/versions)" ]; then
    alembic upgrade head
    echo "Migrations completed successfully!"
else
    echo "No migrations found. Creating tables directly..."
    # Fallback to create_all for initial setup
    python -c "from src.database.database import Base, engine; Base.metadata.create_all(bind=engine)"
    echo "Tables created successfully!"
fi

# Start the application with gunicorn for production
echo "Starting Mimic API server on port ${PORT:-8000}..."

if [ "${APP_ENV}" = "production" ]; then
    # Production: Use gunicorn with multiple workers
    exec gunicorn src.main:app \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:${PORT:-8000} \
        --timeout 60 \
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
