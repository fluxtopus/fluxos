"""Conversation adapter for event-bus orchestrator chat endpoints."""

from __future__ import annotations

import hashlib
import uuid as uuid_mod
from typing import Any, Dict

from src.database.conversation_store import ConversationQuery, ConversationStore
from src.domain.events import OrchestratorConversationPort


class OrchestratorConversationAdapter(OrchestratorConversationPort):
    """Loads orchestrator conversation history by workflow id."""

    def __init__(self, conversation_store: ConversationStore):
        self._conversation_store = conversation_store

    async def get_conversation_history(self, workflow_id: str) -> Dict[str, Any]:
        hash_object = hashlib.md5(workflow_id.encode())
        conversation_uuid = str(uuid_mod.UUID(hash_object.hexdigest()))

        query = ConversationQuery(workflow_id=conversation_uuid)
        conversations = await self._conversation_store.search_conversations(query)
        if not conversations:
            return {
                "conversation_id": None,
                "messages": [],
                "total_messages": 0,
            }

        conversation = conversations[0]
        full_conversation = await self._conversation_store.get_conversation(
            str(conversation.id),
            include_messages=True,
        )
        if not full_conversation:
            return {
                "conversation_id": str(conversation.id),
                "messages": [],
                "total_messages": 0,
            }

        messages: list[Dict[str, Any]] = []
        for msg in full_conversation.messages:
            if msg.message_type.value == "llm_prompt":
                messages.append(
                    {
                        "id": str(msg.id),
                        "type": "user",
                        "content": msg.content_text,
                        "timestamp": msg.timestamp.isoformat(),
                        "sender": msg.agent_id,
                    }
                )
            elif msg.message_type.value == "llm_response":
                messages.append(
                    {
                        "id": str(msg.id),
                        "type": "orchestrator",
                        "content": msg.content_text,
                        "timestamp": msg.timestamp.isoformat(),
                        "sender": "orchestrator",
                    }
                )

        return {
            "conversation_id": str(conversation.id),
            "messages": messages,
            "total_messages": len(messages),
        }

