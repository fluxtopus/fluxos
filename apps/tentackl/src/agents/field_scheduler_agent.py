# REVIEW:
# - This is a demo/mock agent (hard-coded fallback data, mock service URL); unclear if used in production.
import os
from typing import Any, Dict, List

import httpx


class FieldSchedulerAgent:
    """
    Lightweight agent that queries a mock booking system to determine
    affected bookings and propose alternative slots. Falls back to
    deterministic mock data if the service is unavailable.
    """

    def __init__(self, service_url: str | None = None):
        self.service_url = service_url or os.getenv("BOOKING_SERVICE_URL", "http://mock-booking:9001")

    async def execute(self, location: str, affected_hours: List[int]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(
                    f"{self.service_url}/check",
                    json={"location": location, "affected_hours": affected_hours},
                )
                r.raise_for_status()
                data = r.json()
                # Ensure structure
                return {
                    "affected": int(data.get("affected", 0)),
                    "bookings": data.get("bookings", []),
                    "alternatives": data.get("alternatives", []),
                }
        except Exception:
            # Fallback deterministic data
            bookings = [
                {
                    "id": f"BKG-{location[:2].upper()}-{h}-{i+1}",
                    "hour": h,
                    "field": f"Field-{(i % 2) + 1}",
                    "customer": {"name": f"Customer {i+1}", "phone": "+351900000000"},
                }
                for i, h in enumerate(affected_hours[:3])
            ]
            alternatives = []
            for h in affected_hours[:3]:
                for delta in (-1, 1, 2):
                    nh = max(6, min(22, h + delta))
                    alternatives.append({"hour": nh, "field": f"Field-{(nh % 2) + 1}", "reason": "nearby slot"})
            # Dedup
            seen = set()
            dedup = []
            for a in alternatives:
                k = (a["hour"], a["field"])
                if k not in seen:
                    seen.add(k)
                    dedup.append(a)
            return {"affected": len(bookings), "bookings": bookings, "alternatives": dedup[:5]}
