"""Infrastructure adapter for conversation store access."""

from __future__ import annotations

from typing import Optional

from src.domain.inbox.ports import ConversationStorePort
from src.database.conversation_store import ConversationStore


class ConversationStoreAdapter(ConversationStorePort):
    """Adapter exposing ConversationStore through the ConversationStorePort."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    async def get_conversation_user_id(self, conversation_id: str) -> Optional[str]:
        return await self._store.get_conversation_user_id(conversation_id)
