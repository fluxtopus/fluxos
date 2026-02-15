"""Domain ports for agent-related external dependencies."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class AgentConversationReaderPort(Protocol):
    """Port for querying conversations tied to an agent."""

    async def list_agent_conversations(
        self,
        agent_id: str,
        workflow_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        ...
