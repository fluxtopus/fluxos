"""Integration test configuration with isolated database schemas.

This conftest provides database fixtures that create isolated schemas
for integration tests, ensuring test data doesn't pollute the real database
and cleanup happens even when tests fail.
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from src.interfaces.database import Base

# Import all models to register them with Base.metadata
from src.database.capability_models import (  # noqa: F401
    AgentCapability,
    Primitive,
    Plugin,
)
from src.database.task_models import Task, TaskEvent  # noqa: F401
from src.database.memory_models import Memory, MemoryVersion, MemoryPermission  # noqa: F401


def _build_test_db_url() -> str:
    """Resolve the database URL to use for tests."""
    raw_url = os.getenv("TEST_DATABASE_URL") or os.getenv(
        "DATABASE_URL",
        "postgresql://tentackl:tentackl_pass@postgres:5432/aios_tentackl",
    )
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://")
    return raw_url


class IntegrationTestDatabase:
    """Database wrapper for integration tests with isolated schema.

    Provides the same interface as the production Database class
    so it can be used as a drop-in replacement in tests.
    """

    def __init__(self, engine, session_factory, schema_name: str):
        self._engine = engine
        self._session_factory = session_factory
        self._schema_name = schema_name

    async def connect(self) -> None:
        """Provided for interface compatibility."""
        pass

    async def disconnect(self) -> None:
        """Dispose of the engine."""
        await self._engine.dispose()

    def get_session(self) -> AsyncSession:
        """Get a new database session."""
        return self._session_factory()

    async def execute(self, query: str, *args):
        """Execute a raw SQL query."""
        async with self._engine.begin() as conn:
            return await conn.execute(text(query), args)

    async def fetch_one(self, query: str, *args):
        """Fetch a single row."""
        async with self._engine.connect() as conn:
            result = await conn.execute(text(query), args)
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def fetch_many(self, query: str, *args):
        """Fetch multiple rows."""
        async with self._engine.connect() as conn:
            result = await conn.execute(text(query), args)
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]


@pytest_asyncio.fixture
async def integration_db():
    """Provide an isolated PostgreSQL schema for integration tests.

    Creates a unique schema per test, runs all table migrations,
    and drops the schema on cleanup (even if tests fail).

    Usage:
        @pytest.mark.asyncio
        async def test_something(integration_db):
            async with integration_db.get_session() as session:
                # Your test code here
                pass
    """
    database_url = _build_test_db_url()
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    schema_name = f"integration_test_{uuid.uuid4().hex[:12]}"
    schema_created = False
    set_search_path_listener = None
    previous_schema = os.environ.get("DATABASE_SCHEMA")

    try:
        # Create the isolated schema
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        # Set up search path for all connections
        # Test schema first for table resolution, public for pgvector types
        def _set_search_path(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f'SET search_path TO "{schema_name}", public')
            finally:
                cursor.close()

        set_search_path_listener = _set_search_path
        event.listen(engine.sync_engine, "connect", _set_search_path)

        # Create tables in the isolated schema
        async with engine.begin() as conn:
            await conn.execute(text(f'SET search_path TO "{schema_name}", public'))

            # Create tables with checkfirst=False to force creation
            # even though they exist in public schema
            def create_in_test_schema(sync_conn):
                # Create each table individually with explicit schema
                from sqlalchemy import MetaData
                test_metadata = MetaData(schema=schema_name)

                for table in Base.metadata.tables.values():
                    # Create a copy of the table in the test schema
                    table.to_metadata(test_metadata)

                test_metadata.create_all(sync_conn, checkfirst=False)

            await conn.run_sync(create_in_test_schema)
            schema_created = True

        os.environ["DATABASE_SCHEMA"] = schema_name

        db = IntegrationTestDatabase(engine, session_factory, schema_name)
        yield db

    finally:
        if previous_schema is None:
            os.environ.pop("DATABASE_SCHEMA", None)
        else:
            os.environ["DATABASE_SCHEMA"] = previous_schema

        # Always clean up, even on test failure
        try:
            if schema_created:
                async with engine.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        finally:
            await engine.dispose()
            if set_search_path_listener:
                try:
                    event.remove(engine.sync_engine, "connect", set_search_path_listener)
                except Exception:
                    pass


# Alias for backward compatibility with tests expecting 'test_db'
@pytest_asyncio.fixture
async def test_db(integration_db):
    """Alias for integration_db fixture."""
    yield integration_db
