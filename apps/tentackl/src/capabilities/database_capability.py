"""
Database Capability for Tentackl

This module provides database interaction capabilities for agents,
supporting multiple database types with connection pooling and transaction support.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager
import structlog
from urllib.parse import urlparse

# Database drivers (optional imports)
try:
    import asyncpg  # PostgreSQL
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

try:
    import aiomysql  # MySQL
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

try:
    import aiosqlite  # SQLite
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False

try:
    from motor.motor_asyncio import AsyncIOMotorClient  # MongoDB
    HAS_MONGO = True
except ImportError:
    HAS_MONGO = False

from ..interfaces.configurable_agent import AgentCapability
from .capability_registry import ToolDefinition

logger = structlog.get_logger(__name__)


@dataclass
class QueryResult:
    """Result of a database query"""
    rows: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "row_count": self.row_count,
            "columns": self.columns,
            "execution_time_ms": self.execution_time_ms
        }


class DatabaseConnectionPool:
    """Base class for database connection pools"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool = None
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire a connection from the pool"""
        raise NotImplementedError
    
    async def release(self, conn):
        """Release a connection back to the pool"""
        raise NotImplementedError
    
    async def close(self):
        """Close the connection pool"""
        raise NotImplementedError


class PostgresConnectionPool(DatabaseConnectionPool):
    """PostgreSQL connection pool using asyncpg"""
    
    async def initialize(self):
        """Initialize the connection pool"""
        if not HAS_POSTGRES:
            raise ImportError("asyncpg is required for PostgreSQL support")
        
        async with self._lock:
            if not self.pool:
                self.pool = await asyncpg.create_pool(
                    self.config["connection_string"],
                    min_size=self.config.get("min_connections", 1),
                    max_size=self.config.get("max_connections", 10),
                    command_timeout=self.config.get("timeout", 60)
                )
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            yield conn
    
    async def close(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()


class MySQLConnectionPool(DatabaseConnectionPool):
    """MySQL connection pool using aiomysql"""
    
    async def initialize(self):
        """Initialize the connection pool"""
        if not HAS_MYSQL:
            raise ImportError("aiomysql is required for MySQL support")
        
        async with self._lock:
            if not self.pool:
                parsed = urlparse(self.config["connection_string"])
                self.pool = await aiomysql.create_pool(
                    host=parsed.hostname,
                    port=parsed.port or 3306,
                    user=parsed.username,
                    password=parsed.password,
                    db=parsed.path.lstrip('/'),
                    minsize=self.config.get("min_connections", 1),
                    maxsize=self.config.get("max_connections", 10),
                    echo=self.config.get("echo", False)
                )
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                yield cursor
    
    async def close(self):
        """Close the connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()


class DatabaseExecutor:
    """Database query executor with support for multiple database types"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_type = config.get("type", "postgresql")
        self.pool = None
        
        # Query limits
        self.max_rows = config.get("max_rows", 10000)
        self.timeout = config.get("timeout", 60)
        self.read_only = config.get("read_only", False)
        
        # Initialize connection pool based on type
        self._init_pool()
    
    def _init_pool(self):
        """Initialize the appropriate connection pool"""
        if self.db_type == "postgresql":
            self.pool = PostgresConnectionPool(self.config)
        elif self.db_type == "mysql":
            self.pool = MySQLConnectionPool(self.config)
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    async def execute_query(self, query: str, 
                          params: Optional[List[Any]] = None) -> QueryResult:
        """Execute a query and return results"""
        import time
        
        # Check read-only restriction
        if self.read_only and self._is_write_query(query):
            raise ValueError("Write queries not allowed in read-only mode")
        
        start_time = time.time()
        
        if self.db_type == "postgresql":
            return await self._execute_postgres(query, params, start_time)
        elif self.db_type == "mysql":
            return await self._execute_mysql(query, params, start_time)
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    async def _execute_postgres(self, query: str, params: Optional[List[Any]], 
                               start_time: float) -> QueryResult:
        """Execute PostgreSQL query"""
        async with self.pool.acquire() as conn:
            # Execute query
            if params:
                rows = await conn.fetch(query, *params, timeout=self.timeout)
            else:
                rows = await conn.fetch(query, timeout=self.timeout)
            
            # Convert to dicts
            result_rows = [dict(row) for row in rows[:self.max_rows]]
            columns = list(rows[0].keys()) if rows else []
            
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                rows=result_rows,
                row_count=len(result_rows),
                columns=columns,
                execution_time_ms=execution_time
            )
    
    async def _execute_mysql(self, query: str, params: Optional[List[Any]], 
                            start_time: float) -> QueryResult:
        """Execute MySQL query"""
        async with self.pool.acquire() as cursor:
            # Execute query
            await cursor.execute(query, params)
            
            # Fetch results
            if cursor.description:
                rows = await cursor.fetchmany(self.max_rows)
                columns = [desc[0] for desc in cursor.description]
            else:
                rows = []
                columns = []
            
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                rows=rows,
                row_count=len(rows),
                columns=columns,
                execution_time_ms=execution_time
            )
    
    def _is_write_query(self, query: str) -> bool:
        """Check if query is a write operation"""
        write_keywords = ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']
        query_upper = query.strip().upper()
        return any(query_upper.startswith(kw) for kw in write_keywords)
    
    async def execute_transaction(self, queries: List[Tuple[str, Optional[List[Any]]]]) -> List[QueryResult]:
        """Execute multiple queries in a transaction"""
        if self.read_only:
            raise ValueError("Transactions not allowed in read-only mode")
        
        results = []
        
        if self.db_type == "postgresql":
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for query, params in queries:
                        result = await self._execute_postgres(query, params, time.time())
                        results.append(result)
        else:
            raise NotImplementedError(f"Transactions not implemented for {self.db_type}")
        
        return results
    
    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()


class DatabaseCapabilityMethods:
    """Methods that will be injected into agents with database capability"""
    
    def __init__(self, executor: DatabaseExecutor):
        self._executor = executor
    
    async def query(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute a SQL query"""
        try:
            result = await self._executor.execute_query(sql, params)
            return {
                "success": True,
                "data": result.rows,
                "row_count": result.row_count,
                "columns": result.columns,
                "execution_time_ms": result.execution_time_ms
            }
        except Exception as e:
            logger.error("Query execution failed", sql=sql, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "row_count": 0
            }
    
    async def query_one(self, sql: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a query and return the first row"""
        result = await self.query(sql, params)
        if result["success"] and result["data"]:
            return result["data"][0]
        return None
    
    async def execute(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute a SQL statement (for INSERT/UPDATE/DELETE)"""
        return await self.query(sql, params)
    
    async def transaction(self, queries: List[Tuple[str, Optional[List[Any]]]]) -> Dict[str, Any]:
        """Execute multiple queries in a transaction"""
        try:
            results = await self._executor.execute_transaction(queries)
            return {
                "success": True,
                "results": [r.to_dict() for r in results],
                "query_count": len(results)
            }
        except Exception as e:
            logger.error("Transaction failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    async def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """Check if a table exists"""
        if self._executor.db_type == "postgresql":
            query = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = $1 AND table_schema = COALESCE($2, 'public')
                )
            """
            result = await self.query_one(query, [table_name, schema])
            return result and result.get("exists", False)
        else:
            # MySQL implementation
            query = "SHOW TABLES LIKE %s"
            result = await self.query(query, [table_name])
            return result["row_count"] > 0


# Handler function
async def database_handler(config: Dict[str, Any]) -> DatabaseCapabilityMethods:
    """Create database capability methods"""
    executor = DatabaseExecutor(config)
    return DatabaseCapabilityMethods(executor)


# Register the capability
DATABASE_CAPABILITY = ToolDefinition(
    name="database",
    description="Execute database queries with connection pooling and transaction support",
    handler=database_handler,
    config_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["postgresql", "mysql", "sqlite", "mongodb"],
                "description": "Database type"
            },
            "connection_string": {
                "type": "string",
                "description": "Database connection string"
            },
            "max_connections": {
                "type": "integer",
                "default": 10,
                "description": "Maximum connections in pool"
            },
            "min_connections": {
                "type": "integer",
                "default": 1,
                "description": "Minimum connections in pool"
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "description": "Query timeout in seconds"
            },
            "max_rows": {
                "type": "integer",
                "default": 10000,
                "description": "Maximum rows to return"
            },
            "read_only": {
                "type": "boolean",
                "default": False,
                "description": "Restrict to read-only queries"
            }
        },
        "required": ["type", "connection_string"]
    },
    permissions_required=["database:read", "database:write"],
    sandboxable=True,
    category=AgentCapability.CUSTOM
)