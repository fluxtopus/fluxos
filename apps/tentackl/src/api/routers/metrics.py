# REVIEW:
# - initialize_metrics runs at import time; side effects during module import can complicate tests and reloads.
"""Prometheus metrics endpoint for Tentackl."""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import structlog
from src.monitoring.metrics import system_info
import platform
from src.core.config import settings

logger = structlog.get_logger()
router = APIRouter(tags=["monitoring"])


def initialize_metrics():
    """Initialize system information metrics."""
    info = {
        "version": getattr(settings, "VERSION", "unknown"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "environment": getattr(settings, "ENVIRONMENT", "production")
    }
    system_info.info(info)
    logger.info("System info metrics initialized", **info)

# Initialize on module load
initialize_metrics()


@router.get("/metrics", response_class=Response)
async def get_metrics():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format.
    Typically scraped by Prometheus server every 15-30 seconds.
    """
    metrics_data = generate_latest()
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )


@router.get("/health/metrics")
async def metrics_health():
    """
    Health check for metrics system.
    
    Returns basic stats about metrics collection.
    """
    try:
        # Simple check that metrics can be generated
        metrics_data = generate_latest()
        metrics_lines = metrics_data.decode('utf-8').count('\n')
        
        return {
            "status": "healthy",
            "metrics_count": metrics_lines,
            "endpoint": "/metrics"
        }
    except Exception as e:
        logger.error("Metrics health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }
