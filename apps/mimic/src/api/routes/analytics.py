"""Analytics routes"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Annotated, List, Dict, Any
from src.database.database import get_db
from src.database.models import DeliveryLog, ProviderKey
from src.api.auth import require_permission, AuthContext
from datetime import datetime, timedelta

router = APIRouter()


class AnalyticsResponse(BaseModel):
    total_notifications: int
    success_rate: float
    provider_stats: Dict[str, Any]
    daily_stats: List[Dict[str, Any]]
    cost_summary: Dict[str, Any]


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    auth: Annotated[AuthContext, Depends(require_permission("analytics", "view"))],
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get analytics for current user"""
    # Calculate date range
    start_date = datetime.utcnow() - timedelta(days=days)

    # Get all delivery logs for user
    logs = db.query(DeliveryLog).filter(
        DeliveryLog.user_id == auth.user_id,
        DeliveryLog.created_at >= start_date
    ).all()
    
    # Calculate statistics
    total_notifications = len(logs)
    successful = len([log for log in logs if log.status in ["sent", "delivered"]])
    success_rate = (successful / total_notifications * 100) if total_notifications > 0 else 0
    
    # Provider statistics
    provider_stats = {}
    for log in logs:
        if log.provider not in provider_stats:
            provider_stats[log.provider] = {
                "total": 0,
                "successful": 0,
                "failed": 0
            }
        provider_stats[log.provider]["total"] += 1
        if log.status in ["sent", "delivered"]:
            provider_stats[log.provider]["successful"] += 1
        else:
            provider_stats[log.provider]["failed"] += 1
    
    # Daily statistics
    daily_stats = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        day_logs = [log for log in logs if log.created_at.date() == date.date()]
        daily_stats.append({
            "date": date.isoformat(),
            "count": len(day_logs),
            "successful": len([log for log in day_logs if log.status in ["sent", "delivered"]])
        })
    
    # Cost summary
    total_cost = sum(float(log.provider_cost) for log in logs if log.provider_cost)
    cost_summary = {
        "total": total_cost,
        "by_provider": {}
    }
    
    for provider, stats in provider_stats.items():
        provider_logs = [log for log in logs if log.provider == provider]
        provider_cost = sum(float(log.provider_cost) for log in provider_logs if log.provider_cost)
        cost_summary["by_provider"][provider] = provider_cost
    
    return AnalyticsResponse(
        total_notifications=total_notifications,
        success_rate=round(success_rate, 2),
        provider_stats=provider_stats,
        daily_stats=daily_stats,
        cost_summary=cost_summary
    )

