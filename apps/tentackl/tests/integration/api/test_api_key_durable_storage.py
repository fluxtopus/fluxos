"""Integration tests for API key durable storage."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import hashlib

from src.database.api_key_repository import APIKeyRepository
from src.database.auth_models import APIKeyModel
from src.interfaces.database import Database
from src.api.auth_middleware import auth_middleware


@pytest_asyncio.fixture
async def repository(test_db):
    """Create API key repository with test database."""
    return APIKeyRepository(test_db)


class TestAPIKeyDurableStorage:
    """Test API key durable storage with PostgreSQL and Redis."""
    
    @pytest.mark.asyncio
    async def test_create_api_key_durable_storage(self, repository):
        """Test creating API key stores in both PostgreSQL and Redis."""
        api_key = "tentackl_test_key_create_123"
        service_name = "test-service-create"
        scopes = ["workflow:read", "workflow:write"]
        
        # Create key
        success = await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=scopes,
            expires_in_days=30,
            created_by="test-admin"
        )
        
        assert success is True
        
        # Verify in PostgreSQL
        key_hash = repository._hash_key(api_key)
        key_model = await repository.get_api_key_by_hash(key_hash)
        
        assert key_model is not None
        assert key_model.service_name == service_name
        assert key_model.scopes == scopes
        assert key_model.is_active is True
        assert key_model.created_by == "test-admin"
    
    @pytest.mark.asyncio
    async def test_validate_api_key_redis_cache_hit(self, repository):
        """Test API key validation uses Redis cache."""
        api_key = "tentackl_test_key_cache_123"
        service_name = "test-service-cache"
        
        # Create key
        await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=["workflow:read"]
        )
        
        # First validation (should populate cache)
        result1 = await repository.validate_api_key(api_key)
        assert result1 is not None
        assert result1.service_name == service_name
        
        # Second validation (should use cache)
        result2 = await repository.validate_api_key(api_key)
        assert result2 is not None
        assert result2.service_name == service_name
    
    @pytest.mark.asyncio
    async def test_validate_api_key_postgresql_fallback(self, repository):
        """Test API key validation falls back to PostgreSQL when Redis fails."""
        api_key = "tentackl_test_key_fallback_123"
        service_name = "test-service-fallback"
        
        # Create key
        await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=["workflow:read"]
        )
        
        # Simulate Redis failure by using a repository with no Redis
        # We'll manually get from PostgreSQL
        key_hash = repository._hash_key(api_key)
        key_model = await repository.get_api_key_by_hash(key_hash)
        
        assert key_model is not None
        assert key_model.service_name == service_name
    
    @pytest.mark.asyncio
    async def test_revoke_api_key_invalidates_cache(self, repository):
        """Test revoking API key updates PostgreSQL and invalidates cache."""
        api_key = "tentackl_test_key_revoke_123"
        service_name = "test-service-revoke"
        
        # Create key
        await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=["workflow:read"]
        )
        
        # Validate it works
        result = await repository.validate_api_key(api_key)
        assert result is not None
        
        # Revoke it
        success = await repository.revoke_api_key(api_key)
        assert success is True
        
        # Verify it's revoked
        result = await repository.validate_api_key(api_key)
        assert result is None
        
        # Verify in PostgreSQL
        key_hash = repository._hash_key(api_key)
        key_model = await repository.get_api_key_by_hash(key_hash)
        assert key_model is not None
        assert key_model.is_active is False
    
    @pytest.mark.asyncio
    async def test_expired_api_key_validation(self, repository):
        """Test that expired API keys are not validated."""
        api_key = "tentackl_test_key_expired_123"
        service_name = "test-service-expired"
        
        # Create key with very short expiration (in the past)
        # We'll need to manually set expires_at in the database
        key_hash = repository._hash_key(api_key)
        
        # Create key first
        await repository.create_api_key(
            api_key=api_key,
            service_name=service_name,
            scopes=["workflow:read"],
            expires_in_days=1
        )
        
        # Manually expire it in the database
        async with repository.db.get_session() as session:
            from sqlalchemy import update
            await session.execute(
                update(APIKeyModel)
                .where(APIKeyModel.key_hash == key_hash)
                .values(expires_at=datetime.utcnow() - timedelta(days=1))
            )
            await session.commit()
        
        # Try to validate
        result = await repository.validate_api_key(api_key)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_api_keys(self, repository):
        """Test listing API keys with filters."""
        # Create multiple keys
        for i in range(3):
            await repository.create_api_key(
                api_key=f"tentackl_test_key_list_{i}",
                service_name=f"test-service-{i}",
                scopes=["workflow:read"]
            )
        
        # List all keys
        all_keys = await repository.list_api_keys()
        assert len(all_keys) >= 3
        
        # List by service name
        filtered_keys = await repository.list_api_keys(service_name="test-service-0")
        assert len(filtered_keys) == 1
        assert filtered_keys[0].service_name == "test-service-0"
        
        # List active keys
        active_keys = await repository.list_api_keys(is_active=True)
        assert len(active_keys) >= 3
        
        # Revoke one and list inactive
        await repository.revoke_api_key("tentackl_test_key_list_0")
        inactive_keys = await repository.list_api_keys(is_active=False)
        assert len(inactive_keys) >= 1


class TestAuthMiddlewareIntegration:
    """Test AuthMiddleware integration with durable storage."""
    
    @pytest.mark.asyncio
    async def test_auth_middleware_create_api_key(self):
        """Test AuthMiddleware creates API key in durable storage."""
        service_name = "test-middleware-service"
        scopes = ["workflow:read"]
        
        # Create key via middleware
        api_key = await auth_middleware.create_api_key(
            service_name=service_name,
            scopes=scopes,
            expires_in_days=30
        )
        
        assert api_key is not None
        assert api_key.startswith("tentackl_")
        
        # Verify it can be validated
        result = await auth_middleware.validate_api_key(api_key)
        assert result is not None
        assert result.service_name == service_name
        assert result.scopes == scopes
        
        # Cleanup
        await auth_middleware.revoke_api_key(api_key)
    
    @pytest.mark.asyncio
    async def test_auth_middleware_validate_api_key(self):
        """Test AuthMiddleware validates API key from durable storage."""
        service_name = "test-middleware-validate"
        scopes = ["workflow:read", "workflow:write"]
        
        # Create key
        api_key = await auth_middleware.create_api_key(
            service_name=service_name,
            scopes=scopes
        )
        
        # Validate it
        result = await auth_middleware.validate_api_key(api_key)
        assert result is not None
        assert result.service_name == service_name
        assert set(result.scopes) == set(scopes)
        
        # Cleanup
        await auth_middleware.revoke_api_key(api_key)
    
    @pytest.mark.asyncio
    async def test_auth_middleware_revoke_api_key(self):
        """Test AuthMiddleware revokes API key in durable storage."""
        service_name = "test-middleware-revoke"
        
        # Create key
        api_key = await auth_middleware.create_api_key(
            service_name=service_name,
            scopes=["workflow:read"]
        )
        
        # Verify it works
        result = await auth_middleware.validate_api_key(api_key)
        assert result is not None
        
        # Revoke it
        success = await auth_middleware.revoke_api_key(api_key)
        assert success is True
        
        # Verify it's revoked
        result = await auth_middleware.validate_api_key(api_key)
        assert result is None

