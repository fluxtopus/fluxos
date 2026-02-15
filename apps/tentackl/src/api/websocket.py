# REVIEW:
# - json import is unused (minor), and logging is noisy for high-volume events.
"""WebSocket connection management for real-time updates."""

from fastapi import WebSocket
from typing import Dict, Set
import asyncio
import logging
import json

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for workflow monitoring."""
    
    def __init__(self):
        # workflow_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, workflow_id: str):
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        
        async with self._lock:
            if workflow_id not in self.active_connections:
                self.active_connections[workflow_id] = set()
            self.active_connections[workflow_id].add(websocket)
        
        connection_count = len(self.active_connections[workflow_id])
        logger.info(f"🔌 Client connected to workflow '{workflow_id}' (total connections: {connection_count})")
    
    async def disconnect(self, websocket: WebSocket, workflow_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if workflow_id in self.active_connections:
                self.active_connections[workflow_id].discard(websocket)
                remaining_connections = len(self.active_connections[workflow_id])
                if not self.active_connections[workflow_id]:
                    del self.active_connections[workflow_id]
                    logger.info(f"🔌 Client disconnected from workflow '{workflow_id}' (no more connections)")
                else:
                    logger.info(f"🔌 Client disconnected from workflow '{workflow_id}' ({remaining_connections} connections remaining)")
            else:
                logger.warning(f"⚠️ Attempted to disconnect from unknown workflow '{workflow_id}'")
    
    async def send_to_workflow(self, workflow_id: str, message: dict):
        """Send a message to all clients monitoring a workflow."""
        async with self._lock:
            connections = self.active_connections.get(workflow_id, set()).copy()
        
        if connections:
            message_type = message.get('type', 'unknown')
            logger.info(f"📤 Sending '{message_type}' message to {len(connections)} client(s) for workflow '{workflow_id}'")
            
            # Send to all connections in parallel
            tasks = []
            for connection in connections:
                tasks.append(self._send_json_safe(connection, message, workflow_id))
            
            await asyncio.gather(*tasks)
        else:
            message_type = message.get('type', 'unknown')
            logger.warning(f"📪 No clients connected to workflow '{workflow_id}' for '{message_type}' message")
    
    async def _send_json_safe(self, websocket: WebSocket, message: dict, workflow_id: str):
        """Safely send JSON message to a WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to client on workflow {workflow_id}: {e}")
            await self.disconnect(websocket, workflow_id)
    
    async def broadcast(self, workflow_id: str, message: dict):
        """Broadcast a message to all clients monitoring a specific workflow."""
        await self.send_to_workflow(workflow_id, message)
    
    async def disconnect_all(self):
        """Disconnect all clients gracefully."""
        async with self._lock:
            all_connections = []
            for workflow_id, connections in self.active_connections.items():
                for connection in connections:
                    all_connections.append((connection, workflow_id))
            
            self.active_connections.clear()
        
        # Send disconnect message to all
        disconnect_msg = {"type": "server_shutdown", "message": "Server is shutting down"}
        for connection, workflow_id in all_connections:
            try:
                await connection.send_json(disconnect_msg)
                await connection.close()
            except Exception as e:
                logger.error(f"Error disconnecting client from workflow {workflow_id}: {e}")
        
        logger.info("All WebSocket connections closed")
    
    def get_connection_count(self) -> Dict[str, int]:
        """Get the number of connections per workflow."""
        return {
            workflow_id: len(connections)
            for workflow_id, connections in self.active_connections.items()
        }
