"""Billing routes for Mimic notification service."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/billing/status")
async def get_billing_status():
    """Get billing status - placeholder for future implementation."""
    return {"status": "ok", "message": "Billing managed via the platform"}
