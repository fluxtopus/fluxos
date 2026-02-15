"""Mock Discord webhook server for testing"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import structlog
from typing import Dict, Any
from datetime import datetime

logger = structlog.get_logger()

app = FastAPI(title="Mock Discord Webhook Server")

# Store received messages for verification
received_messages = []


@app.post("/webhooks/{webhook_id}/{webhook_token}")
async def discord_webhook(webhook_id: str, webhook_token: str, request: Request):
    """Mock Discord webhook endpoint"""
    try:
        payload = await request.json()
        message = {
            "webhook_id": webhook_id,
            "webhook_token": webhook_token,
            "payload": payload,
            "received_at": datetime.utcnow().isoformat(),
            "headers": dict(request.headers)
        }
        received_messages.append(message)
        
        logger.info("Mock Discord webhook received", 
                   webhook_id=webhook_id,
                   payload_keys=list(payload.keys()))
        
        # Discord returns 204 No Content on success
        return JSONResponse(
            content=None,
            status_code=204
        )
    except Exception as e:
        logger.error("Error processing Discord webhook", error=str(e))
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/messages")
async def get_messages():
    """Get all received messages (for testing)"""
    return {
        "count": len(received_messages),
        "messages": received_messages
    }


@app.delete("/messages")
async def clear_messages():
    """Clear all received messages (for testing)"""
    global received_messages
    received_messages = []
    return {"message": "Messages cleared", "count": 0}


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "mock-discord-server"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

