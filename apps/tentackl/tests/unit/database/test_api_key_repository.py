"""Unit tests for API key repository."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.database.api_key_repository import APIKeyRepository
from src.database.auth_models import APIKeyModel
from src.interfaces.database import Database


@pytest.fixture
def mock_database():
    """Create a mock database."""
    db = MagicMock(spec=Database)
    db.get_session = MagicMock()
    return db


@pytest.fixture
def repository(mock_database):
    """Create API key repository with mock database."""
    return APIKeyRepository(mock_database)


class TestAPIKeyRepository:
    """Test API key repository operations."""
    
    @pytest.mark.asyncio
    async def test_hash_key(self, repository):
        """Test key hashing."""
        key = "test_key_123"
        hash1 = repository._hash_key(key)
        hash2 = repository._hash_key(key)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
        assert hash1 != repository._hash_key("different_key")
    
    @pytest.mark.asyncio
    async def test_serialize_deserialize_key_data(self, repository):
        """Test serialization and deserialization of key data."""
        key_model = APIKeyModel(
            key_hash="test_hash",
            service_name="test-service",
            scopes=["scope1", "scope2"],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=1),
            is_active=True,
            created_by="admin",
            metadata={"key": "value"}
        )
        
        # Serialize
        serialized = repository._serialize_key_data(key_model)
        assert isinstance(serialized, str)
        
        # Deserialize
        deserialized = repository._deserialize_key_data(serialized)
        assert deserialized is not None
        assert deserialized["service_name"] == "test-service"
        assert deserialized["scopes"] == ["scope1", "scope2"]
        assert deserialized["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_create_api_key(self, repository, mock_database):
        """Test creating an API key."""
        # Mock session
        mock_session = AsyncMock()
        mock_database.get_session.return_value.__aenter__.return_value = mock_session
        mock_database.get_session.return_value.__aexit__.return_value = None
        
        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.ping = AsyncMock()
        
        with patch.object(repository, '_get_redis', return_value=mock_redis):
            key = "tentackl_test_key_123"
            success = await repository.create_api_key(
                api_key=key,
                service_name="test-service",
                scopes=["scope1"],
                expires_in_days=30,
                created_by="admin"
            )
            
            assert success is True
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_api_key_by_hash_redis_hit(self, repository, mock_database):
        """Test getting API key from Redis cache."""
        key_hash = "test_hash_123"
        
        # Mock Redis with cached data
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value='{"service_name": "test-service", "scopes": ["scope1"]}')
        mock_redis.ping = AsyncMock()
        
        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_key_model = APIKeyModel(
            key_hash=key_hash,
            service_name="test-service",
            scopes=["scope1"],
            created_at=datetime.utcnow(),
            is_active=True
        )
        mock_result.scalar_one_or_none.return_value = mock_key_model
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_database.get_session.return_value.__aenter__.return_value = mock_session
        mock_database.get_session.return_value.__aexit__.return_value = None
        
        with patch.object(repository, '_get_redis', return_value=mock_redis):
            result = await repository.get_api_key_by_hash(key_hash)
            
            assert result is not None
            assert result.service_name == "test-service"
            mock_redis.hget.assert_called_once_with("api_keys", key_hash)
    
    @pytest.mark.asyncio
    async def test_get_api_key_by_hash_postgresql_fallback(self, repository, mock_database):
        """Test getting API key from PostgreSQL when Redis fails."""
        key_hash = "test_hash_123"
        
        # Mock Redis failure
        with patch.object(repository, '_get_redis', return_value=None):
            # Mock database session
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_key_model = APIKeyModel(
                key_hash=key_hash,
                service_name="test-service",
                scopes=["scope1"],
                created_at=datetime.utcnow(),
                is_active=True
            )
            mock_result.scalar_one_or_none.return_value = mock_key_model
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_database.get_session.return_value.__aenter__.return_value = mock_session
            mock_database.get_session.return_value.__aexit__.return_value = None
            
            result = await repository.get_api_key_by_hash(key_hash)
            
            assert result is not None
            assert result.service_name == "test-service"
    
    @pytest.mark.asyncio
    async def test_validate_api_key(self, repository, mock_database):
        """Test validating an API key."""
        api_key = "tentackl_test_key_123"
        key_hash = repository._hash_key(api_key)
        
        # Mock get_api_key_by_hash
        mock_key_model = APIKeyModel(
            key_hash=key_hash,
            service_name="test-service",
            scopes=["scope1"],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=1),
            is_active=True
        )
        
        with patch.object(repository, 'get_api_key_by_hash', return_value=mock_key_model):
            # Mock session for last_used_at update
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_database.get_session.return_value.__aenter__.return_value = mock_session
            mock_database.get_session.return_value.__aexit__.return_value = None
            
            result = await repository.validate_api_key(api_key)
            
            assert result is not None
            assert result.service_name == "test-service"
            assert result.is_active is True
    
    @pytest.mark.asyncio
    async def test_validate_api_key_expired(self, repository):
        """Test validating an expired API key."""
        api_key = "tentackl_test_key_123"
        
        # Mock expired key
        mock_key_model = APIKeyModel(
            key_hash=repository._hash_key(api_key),
            service_name="test-service",
            scopes=["scope1"],
            created_at=datetime.utcnow() - timedelta(days=2),
            expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
            is_active=True
        )
        
        with patch.object(repository, 'get_api_key_by_hash', return_value=mock_key_model):
            result = await repository.validate_api_key(api_key)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_validate_api_key_inactive(self, repository):
        """Test validating an inactive API key."""
        api_key = "tentackl_test_key_123"
        
        # Mock inactive key
        mock_key_model = APIKeyModel(
            key_hash=repository._hash_key(api_key),
            service_name="test-service",
            scopes=["scope1"],
            created_at=datetime.utcnow(),
            is_active=False  # Inactive
        )
        
        with patch.object(repository, 'get_api_key_by_hash', return_value=mock_key_model):
            result = await repository.validate_api_key(api_key)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_revoke_api_key(self, repository, mock_database):
        """Test revoking an API key."""
        api_key = "tentackl_test_key_123"
        
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_database.get_session.return_value.__aenter__.return_value = mock_session
        mock_database.get_session.return_value.__aexit__.return_value = None
        
        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.hdel = AsyncMock()
        mock_redis.ping = AsyncMock()
        
        with patch.object(repository, '_get_redis', return_value=mock_redis):
            success = await repository.revoke_api_key(api_key)
            
            assert success is True
            mock_session.commit.assert_called_once()
            mock_redis.hdel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_api_keys(self, repository, mock_database):
        """Test listing API keys."""
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_key1 = APIKeyModel(
            key_hash="hash1",
            service_name="service1",
            scopes=["scope1"],
            created_at=datetime.utcnow(),
            is_active=True
        )
        mock_key2 = APIKeyModel(
            key_hash="hash2",
            service_name="service2",
            scopes=["scope2"],
            created_at=datetime.utcnow(),
            is_active=True
        )
        mock_result.scalars.return_value.all.return_value = [mock_key1, mock_key2]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_database.get_session.return_value.__aenter__.return_value = mock_session
        mock_database.get_session.return_value.__aexit__.return_value = None
        
        result = await repository.list_api_keys()
        
        assert len(result) == 2
        assert result[0].service_name == "service1"
        assert result[1].service_name == "service2"


