"""Pytest configuration and fixtures"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
import os

from src.main import app
from src.database.database import Base, get_db
from src.database.models import User, APIKey, ProviderKey, Template, Workflow, DeliveryLog
from src.api.routes.auth import hash_api_key
from src.api.auth import get_current_user, AuthContext
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)
from src.services.key_encryption import KeyEncryptionService


# Test database URL (in-memory SQLite for unit tests)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test engine
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create test session factory
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def override_get_db(db_session):
    """Override get_db dependency"""
    def _get_db():
        try:
            yield db_session
        finally:
            pass
    return _get_db


@pytest.fixture
def client(override_get_db):
    """Create test client"""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        id="test-user-123",
        email="test@example.com",
        password_hash=get_password_hash("testpassword123"),
        subscription_tier="free",
        subscription_expires_at=None
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_annual(db_session):
    """Create a test user with annual subscription"""
    user = User(
        id="test-user-annual-123",
        email="annual@example.com",
        password_hash=get_password_hash("testpassword123"),
        subscription_tier="annual",
        subscription_expires_at=datetime.utcnow() + timedelta(days=365)
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_api_key(db_session, test_user):
    """Create a test API key"""
    api_key_value = "test-api-key-12345"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        id="test-api-key-123",
        user_id=test_user.id,
        key_hash=key_hash,
        name="Test API Key",
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    return api_key, api_key_value


@pytest.fixture
def test_provider_key(db_session, test_user_annual):
    """Create a test provider key (encrypted)"""
    encryption_service = KeyEncryptionService()
    encrypted_key = encryption_service.encrypt("test-sendgrid-api-key")
    
    provider_key = ProviderKey(
        id="test-provider-key-123",
        user_id=test_user_annual.id,
        provider_type="email",
        encrypted_api_key=encrypted_key,
        from_email="test@example.com",
        is_active=True
    )
    db_session.add(provider_key)
    db_session.commit()
    db_session.refresh(provider_key)
    return provider_key


@pytest.fixture
def mock_inkpass_auth(db_session):
    """Mock InkPass auth by overriding get_current_user to look up API keys locally.

    This allows tests that send Bearer tokens with local API key values to work
    without a running InkPass service.
    """
    from fastapi import Request
    import src.api.auth as auth_module

    async def _mock_get_current_user(
        request: Request,
    ):
        from fastapi import HTTPException
        # Extract bearer token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            key_hash = hash_api_key(token)
            api_key_obj = db_session.query(APIKey).filter(APIKey.key_hash == key_hash).first()
            if api_key_obj:
                user = db_session.query(User).filter(User.id == api_key_obj.user_id).first()
                return AuthContext(
                    user_id=api_key_obj.user_id,
                    email=user.email if user else "",
                    organization_id="test-org",
                    auth_type="api_key",
                    token=token,
                )
        raise HTTPException(status_code=401, detail="Authentication required")

    # Mock InkPass client to bypass permission checks
    class MockInkPassClient:
        async def check_permission(self, token: str, resource: str, action: str) -> bool:
            return True  # Always allow in tests

        async def validate_token(self, token: str):
            return None  # Not used since we override get_current_user

        async def validate_api_key(self, api_key: str):
            return None  # Not used since we override get_current_user

    # Replace the InkPass client singleton
    original_client = auth_module._inkpass_client
    auth_module._inkpass_client = MockInkPassClient()

    app.dependency_overrides[get_current_user] = _mock_get_current_user
    yield
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    auth_module._inkpass_client = original_client


@pytest.fixture
def mock_tentackl_client():
    """Mock Tentackl client"""
    # Some routes import TentacklClient directly (e.g. notifications.py), so patch both the
    # original module and the already-imported symbol.
    with patch("src.clients.tentackl_client.TentacklClient") as mock_client_cls, patch(
        "src.api.routes.notifications.TentacklClient"
    ) as mock_notifications_cls:
        for mock_cls in (mock_client_cls, mock_notifications_cls):
            instance = mock_cls.return_value
            instance.send_notification = AsyncMock(return_value="workflow-run-123")
            instance.trigger_workflow = AsyncMock(return_value="workflow-run-456")
            instance.get_workflow_status = AsyncMock(
                return_value={
                    "workflow_id": "workflow-run-123",
                    "status": "completed",
                }
            )

        yield mock_notifications_cls.return_value


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for external API calls"""
    with patch('httpx.AsyncClient') as mock:
        yield mock


@pytest.fixture
def mock_stripe():
    """Mock Stripe service"""
    with patch('src.services.stripe_service.stripe') as mock:
        yield mock


@pytest.fixture(autouse=True)
def reset_encryption_key():
    """Reset encryption key for tests"""
    # Set a test encryption key
    os.environ["ENCRYPTION_KEY"] = "test-key-32-characters-long!!"
    yield
    # Cleanup
    if "ENCRYPTION_KEY" in os.environ:
        del os.environ["ENCRYPTION_KEY"]


@pytest.fixture(autouse=True)
def reset_inkpass_singleton():
    """Reset InkPass client singleton between tests to prevent state pollution."""
    import src.api.auth as auth_module
    auth_module._inkpass_client = None
    yield
    auth_module._inkpass_client = None


@pytest.fixture(autouse=True)
def mock_celery_tasks():
    """Prevent unit tests from calling Celery brokers via .delay()."""
    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-test")
        yield
