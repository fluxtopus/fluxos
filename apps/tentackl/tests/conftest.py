"""Test configuration and fixtures."""

import os
import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from src.api.app import setup_api_routes
from src.interfaces.database import Base
# Import models to ensure they're registered with Base.metadata
from src.database.allowed_host_models import AllowedHost  # noqa: F401
from src.database.task_models import Task, CheckpointApproval, UserPreference, TaskEvent, ObserverReport  # noqa: F401

# Enable dev auth bypass for all tests (SEC-010: now requires token as second factor)
os.environ["DEV_AUTH_BYPASS"] = "true"
os.environ["DEV_AUTH_BYPASS_TOKEN"] = "test-bypass-token"

# Patch auth_middleware.require_auth globally for all tests
# This ensures tests that create their own FastAPI apps also get auth bypass
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_test_auth():
    """Setup test authentication bypass for all tests."""
    from src.api.auth_middleware import auth_middleware, AuthUser, DEVELOPER_SCOPES
    
    # Create a dev user that will be returned by require_auth
    dev_user = AuthUser(
        id="dev",
        auth_type="none",
        username="developer",
        scopes=DEVELOPER_SCOPES,
        metadata={"auto_dev_user": True}
    )
    
    # Store original method
    original_require_auth = auth_middleware.require_auth
    
    def mock_require_auth(required_scopes=None):
        """Mock require_auth that always returns dev user."""
        async def auth_dependency(request):
            # Set auth user in request state
            request.state.auth_user = dev_user
            request.state.auth_type = "none"
            return dev_user
        return auth_dependency
    
    # Patch the method
    auth_middleware.require_auth = mock_require_auth
    
    yield
    
    # Restore original method after all tests
    auth_middleware.require_auth = original_require_auth


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for testing."""
    # Create conversation store mock
    conversation_store_mock = AsyncMock()
    conversation_store_mock.search_conversations.return_value = []

    return {
        'database': MagicMock(),
        'conversation_store': conversation_store_mock,
        'event_bus': MagicMock(),
        'event_gateway': MagicMock(),
    }


@pytest.fixture
def test_app(mock_dependencies):
    """Create a test app with mocked dependencies."""
    from fastapi import FastAPI
    from src.api.cors_config import configure_cors
    
    # Create a fresh FastAPI app for testing
    app = FastAPI(title="Test Tentackl API", version="0.1.0")
    configure_cors(app)
    
    # Setup API routes with mock dependencies
    import asyncio
    asyncio.run(setup_api_routes(app, **mock_dependencies))
    
    return app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    with TestClient(test_app) as test_client:
        yield test_client


def _build_test_db_url() -> str:
    """Resolve the database URL to use for tests."""
    raw_url = os.getenv("TEST_DATABASE_URL") or os.getenv(
        "DATABASE_URL",
        "postgresql://tentackl:tentackl_pass@postgres:5432/tentackl_db",
    )
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://")
    return raw_url


class AsyncTestDatabase:
    """Lightweight async database wrapper for tests."""

    def __init__(self, engine, session_factory):
        self._engine = engine
        self._session_factory = session_factory

    async def connect(self) -> None:
        """Provided for interface compatibility."""

    async def disconnect(self) -> None:
        await self._engine.dispose()

    def get_session(self) -> AsyncSession:
        return self._session_factory()

    async def execute(self, query: str, *args):
        async with self._engine.begin() as conn:
            return await conn.execute(text(query), args)

    async def fetch_one(self, query: str, *args):
        async with self._engine.connect() as conn:
            result = await conn.execute(text(query), args)
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def fetch_many(self, query: str, *args):
        async with self._engine.connect() as conn:
            result = await conn.execute(text(query), args)
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]


@pytest_asyncio.fixture
async def test_db():
    """Provide an isolated PostgreSQL schema for database tests."""
    database_url = _build_test_db_url()
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    schema_name = f"test_{uuid.uuid4().hex}"

    try:
        schema_created = False
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        @event.listens_for(engine.sync_engine, "connect")
        def _set_search_path(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                # Include public schema so pg_vector types are accessible
                cursor.execute(f'SET search_path TO "{schema_name}", public')
            finally:
                cursor.close()

        async with engine.begin() as conn:
            # Include public schema so pg_vector types are accessible
            await conn.execute(text(f'SET search_path TO "{schema_name}", public'))
            await conn.run_sync(Base.metadata.create_all)
            schema_created = True

        db = AsyncTestDatabase(engine, session_factory)
        yield db
    finally:
        try:
            async with engine.begin() as conn:
                if 'schema_created' in locals() and schema_created:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        finally:
            await engine.dispose()
            try:
                event.remove(engine.sync_engine, "connect", _set_search_path)
            except Exception:
                pass


@pytest.fixture
def sample_conversation_data():
    """Provide reusable conversation fixture data."""
    workflow_id = str(uuid.uuid4())
    return {
        "workflow_id": workflow_id,
        "root_agent_id": "test_agent",
        "trigger": {
            "source": "webhook_source",
            "details": {
                "event": "test_event",
                "severity": "info",
                "metadata": {"location": "Porto"},
            },
        },
    }


@pytest.fixture
def sample_message_data():
    """Provide reusable message fixture data."""
    return {
        "agent_id": "agent_123",
        "content": {
            "role": "assistant",
            "text": "Processing request",
            "data": {"step": "analysis", "confidence": 0.92},
        },
        "metadata": {
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "tokens": {"prompt": 120, "completion": 60, "total": 180},
            "latency_ms": 150,
        },
        "cost": {"amount": 0.0045, "currency": "USD"},
    }
