"""
State Persistence Capability Implementation

Provides state persistence for agents using Redis.
Extracted from StatefulAgent._load_state, _save_state, _auto_save_loop.
"""

import asyncio
from typing import Any, Dict, Optional, Callable, Awaitable
from datetime import datetime
import structlog

from src.capabilities.protocols import StatePersistenceCapability, StateSnapshot
from src.interfaces.state_store import StateStoreInterface, StateSnapshot as IStateSnapshot, StateType

logger = structlog.get_logger(__name__)


class StatePersistenceImpl:
    """
    Implementation of state persistence capability.

    Wraps StateStoreInterface to provide state persistence for agents.
    Supports auto-save functionality for periodic state snapshots.
    """

    def __init__(self, state_store: StateStoreInterface):
        """
        Initialize state persistence.

        Args:
            state_store: The underlying state store (e.g., RedisStateStore)
        """
        self._store = state_store
        self._auto_save_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def save_state(
        self,
        agent_id: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save current agent state."""
        try:
            snapshot = IStateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data=state.copy(),
                metadata=metadata or {}
            )

            await self._store.save_state(snapshot)
            logger.debug("State saved", agent_id=agent_id)
            return True

        except Exception as e:
            logger.error("Failed to save state", agent_id=agent_id, error=str(e))
            return False

    async def load_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Load the latest state for an agent."""
        try:
            latest_state = await self._store.get_latest_state(
                agent_id, StateType.AGENT_STATE
            )

            if latest_state:
                logger.debug("State loaded", agent_id=agent_id)
                return latest_state.data.copy()

            return None

        except Exception as e:
            logger.warning("Failed to load state", agent_id=agent_id, error=str(e))
            return None

    async def start_auto_save(
        self,
        agent_id: str,
        interval_seconds: int,
        get_state_fn: Callable[[], Awaitable[Dict[str, Any]]]
    ) -> None:
        """Start automatic state saving at regular intervals."""
        if self._auto_save_task and not self._auto_save_task.done():
            logger.warning("Auto-save already running", agent_id=agent_id)
            return

        self._shutdown_event.clear()
        self._auto_save_task = asyncio.create_task(
            self._auto_save_loop(agent_id, interval_seconds, get_state_fn)
        )
        logger.info("Auto-save started", agent_id=agent_id, interval=interval_seconds)

    async def stop_auto_save(self) -> None:
        """Stop the auto-save loop if running."""
        self._shutdown_event.set()

        if self._auto_save_task and not self._auto_save_task.done():
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass

        self._auto_save_task = None
        logger.debug("Auto-save stopped")

    async def _auto_save_loop(
        self,
        agent_id: str,
        interval_seconds: int,
        get_state_fn: Callable[[], Awaitable[Dict[str, Any]]]
    ) -> None:
        """Internal auto-save loop."""
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(interval_seconds)

                if not self._shutdown_event.is_set():
                    try:
                        state = await get_state_fn()
                        await self.save_state(agent_id, state)
                    except Exception as e:
                        logger.error("Auto-save failed", agent_id=agent_id, error=str(e))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Auto-save loop error", agent_id=agent_id, error=str(e))

    async def delete_state(self, agent_id: str) -> bool:
        """Delete all state for an agent."""
        try:
            # Use state store's delete functionality if available
            if hasattr(self._store, 'delete_agent_state'):
                await self._store.delete_agent_state(agent_id)
            return True
        except Exception as e:
            logger.error("Failed to delete state", agent_id=agent_id, error=str(e))
            return False

    async def get_state_history(
        self,
        agent_id: str,
        limit: int = 10
    ) -> list:
        """Get state history for an agent."""
        try:
            from src.interfaces.state_store import StateQuery
            query = StateQuery(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                limit=limit
            )
            states = await self._store.load_state(query)
            return [
                StateSnapshot(
                    agent_id=s.agent_id,
                    data=s.data,
                    timestamp=s.created_at or datetime.utcnow(),
                    metadata=s.metadata
                )
                for s in states
            ]
        except Exception as e:
            logger.error("Failed to get state history", agent_id=agent_id, error=str(e))
            return []

    @property
    def store(self) -> StateStoreInterface:
        """Access the underlying state store."""
        return self._store
