# REVIEW:
# - Health checks open new DB/Redis connections per request without timeouts; may become expensive under load.
# - Redis client close uses close(); in redis.asyncio recommended aclose().
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
import asyncpg
import redis.asyncio as redis
from src.core.config import settings
import structlog

logger = structlog.get_logger()
health_router = APIRouter()


async def check_database() -> Dict[str, Any]:
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        await conn.fetchval("SELECT 1")
        await conn.close()
        return {"status": "healthy", "service": "postgres"}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "service": "postgres", "error": str(e)}


async def check_redis() -> Dict[str, Any]:
    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        return {"status": "healthy", "service": "redis"}
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        return {"status": "unhealthy", "service": "redis", "error": str(e)}


@health_router.get("")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
    }
    
    overall_status = all(check["status"] == "healthy" for check in checks.values())
    
    return JSONResponse(
        status_code=status.HTTP_200_OK if overall_status else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "healthy" if overall_status else "unhealthy",
            "checks": checks
        }
    )


@health_router.get("/live")
async def liveness():
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "alive"}
    )


@health_router.get("/ready")
async def readiness():
    db_check = await check_database()
    redis_check = await check_redis()
    
    is_ready = (
        db_check["status"] == "healthy" and 
        redis_check["status"] == "healthy"
    )
    
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "ready": is_ready,
            "dependencies": {
                "database": db_check["status"],
                "redis": redis_check["status"]
            }
        }
    )
