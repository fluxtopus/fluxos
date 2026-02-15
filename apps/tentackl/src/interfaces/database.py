# REVIEW: Database helpers expose raw SQL execution with positional args passed
# REVIEW: into `text()` without explicit parameter binding conventions, which can
# REVIEW: encourage unsafe query construction. Consider typed repositories or
# REVIEW: enforcing bind parameters.
from abc import ABC, abstractmethod
import os
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event
from sqlalchemy.orm import declarative_base
from src.core.config import settings
import structlog

logger = structlog.get_logger()
Base = declarative_base()


class DatabaseInterface(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        pass
    
    @abstractmethod
    async def execute(self, query: str, *args) -> Any:
        pass
    
    @abstractmethod
    async def fetch_one(self, query: str, *args) -> Optional[Dict]:
        pass
    
    @abstractmethod
    async def fetch_many(self, query: str, *args) -> List[Dict]:
        pass


class Database(DatabaseInterface):
    def __init__(self):
        # Some providers use postgres:// but SQLAlchemy requires postgresql://
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        # Add asyncpg driver for async SQLAlchemy
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        self.engine = create_async_engine(
            db_url,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,  # Verify connections before using them
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=settings.APP_ENV == "development"
        )

        schema = os.getenv("DATABASE_SCHEMA")
        if schema:
            # Allow only safe schema identifiers.
            if not re.fullmatch(r"[A-Za-z0-9_]+", schema):
                raise ValueError("DATABASE_SCHEMA contains invalid characters")

            def _set_search_path(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f'SET search_path TO "{schema}", public')
                finally:
                    cursor.close()

            event.listen(self.engine.sync_engine, "connect", _set_search_path)

        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def connect(self) -> None:
        """Initialize database connection (SQLAlchemy handles pooling automatically)"""
        try:
            # Test the connection
            from sqlalchemy import text
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error("Failed to connect to database", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close database connections and dispose of the engine"""
        await self.engine.dispose()
        logger.info("SQLAlchemy engine disposed")
    
    async def execute(self, query: str, *args) -> Any:
        """Execute a raw SQL query using SQLAlchemy"""
        async with self.engine.begin() as conn:
            from sqlalchemy import text
            return await conn.execute(text(query), args)

    async def fetch_one(self, query: str, *args) -> Optional[Dict]:
        """Fetch one row from a query using SQLAlchemy"""
        async with self.engine.connect() as conn:
            from sqlalchemy import text
            result = await conn.execute(text(query), args)
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def fetch_many(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows from a query using SQLAlchemy"""
        async with self.engine.connect() as conn:
            from sqlalchemy import text
            result = await conn.execute(text(query), args)
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    def get_session(self) -> AsyncSession:
        """Get a new SQLAlchemy async session"""
        return self.async_session()
