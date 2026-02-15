#!/bin/bash
# Script to initialize multiple PostgreSQL databases
# Used by docker-compose to create separate databases for each service

set -e
set -u

function create_database() {
    local database=$1
    echo "Creating database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE $database;
        GRANT ALL PRIVILEGES ON DATABASE $database TO $POSTGRES_USER;
EOSQL
}

if [ -n "${POSTGRES_MULTIPLE_DATABASES:-}" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
    for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
        create_database $db
    done
    echo "Multiple databases created"
else
    # Default databases for local development
    create_database aios_inkpass
    create_database aios_tentackl
    create_database aios_mimic
    echo "Default databases created: aios_inkpass, aios_tentackl, aios_mimic"
fi

# Enable extensions for semantic search (pgvector) and text search (pg_trgm)
echo "Enabling extensions for aios_inkpass database..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname aios_inkpass <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOSQL
echo "Extensions enabled: vector, pg_trgm"
