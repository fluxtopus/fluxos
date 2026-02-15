"""Pytest configuration and fixtures"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import os

# Disable rate limiting BEFORE importing app (which calls init_redis on startup)
from src.middleware import rate_limiting
rate_limiting.init_redis = lambda: None  # No-op to prevent Redis initialization

# Mock notification service to avoid mimic dependency
from src.services import notification_service
notification_service.NotificationService.send_email = AsyncMock(return_value=True)
notification_service.NotificationService.send_email_verification = AsyncMock(return_value=True)

from src.database.database import Base, get_db
from src.main import app
from src.config import settings

# Also ensure redis_client stays None
rate_limiting.redis_client = None

# Use test database - use same credentials as app
# The database should exist and have migrations applied
_db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_master_pass@postgres:5432/inkpass")
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", _db_url)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create a test database session with transaction rollback for isolation."""
    # Ensure tables exist (won't error if already exist)
    Base.metadata.create_all(bind=engine)

    # Create connection and begin transaction
    connection = engine.connect()
    transaction = connection.begin()

    # Create session bound to transaction
    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()  # Roll back all changes
        connection.close()


@pytest.fixture(scope="function")
def client(db):
    """Create a test client with database session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_token(client, db):
    """Create a user and return their auth token for file tests."""
    import uuid
    from src.database.models import User
    unique_email = f"test-{uuid.uuid4().hex[:8]}@example.com"

    # Register user
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "TestPassword123!",
            "organization_name": f"Test Org {uuid.uuid4().hex[:6]}"
        }
    )

    if response.status_code != 201:
        raise Exception(f"Failed to register: {response.json()}")

    # Activate user directly in database (bypass email verification for tests)
    user = db.query(User).filter(User.email == unique_email).first()
    if user:
        user.status = "active"
        db.commit()

    # Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": unique_email,
            "password": "TestPassword123!"
        }
    )

    if login_response.status_code != 200:
        raise Exception(f"Failed to login: {login_response.json()}")

    return login_response.json()["access_token"]


@pytest.fixture(scope="function")
def auth_headers(auth_token):
    """Return auth headers for requests."""
    return {"Authorization": f"Bearer {auth_token}"}
