"""Conversation store adapter for agent application use cases."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.database.conversation_store import ConversationQuery, ConversationStore
from src.domain.agents import AgentConversationReaderPort


class ConversationStoreAgentReaderAdapter(AgentConversationReaderPort):
    """Adapter exposing agent conversation reads through a domain port."""

    def __init__(self, conversation_store: ConversationStore) -> None:
        self._conversation_store = conversation_store

    async def list_agent_conversations(
        self,
        agent_id: str,
        workflow_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        query = ConversationQuery(root_agent_id=agent_id, workflow_id=workflow_id)
        conversations = await self._conversation_store.search_conversations(query)

        result: List[Dict[str, Any]] = []
        for conversation in conversations:
            conversation_view = await self._conversation_store.get_conversation(
                str(conversation.id),
                include_messages=True,
            )
            message_counts: Dict[str, int] = {}
            for message in conversation_view.messages:
                message_type = getattr(message.message_type, "value", str(message.message_type))
                message_counts[message_type] = message_counts.get(message_type, 0) + 1

            workflow = getattr(conversation, "workflow_id", None)
            result.append(
                {
                    "id": str(conversation.id),
                    "workflow_id": str(workflow) if workflow is not None else None,
                    "agent_id": conversation.root_agent_id,
                    "start_time": conversation.start_time.isoformat(),
                    "end_time": (
                        conversation.end_time.isoformat() if conversation.end_time else None
                    ),
                    "status": getattr(conversation.status, "value", str(conversation.status)),
                    "message_counts": message_counts,
                    "total_messages": len(conversation_view.messages),
                }
            )

        return result
