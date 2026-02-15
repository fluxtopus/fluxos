"""Infrastructure adapter for inbox chat streaming."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from src.database.conversation_store import ConversationStore
from src.domain.inbox.ports import InboxChatPort
from src.infrastructure.inbox.inbox_chat_service import InboxChatService


class InboxChatServiceAdapter(InboxChatPort):
    """Adapter exposing InboxChatService through the InboxChatPort."""

    def __init__(self, store: ConversationStore) -> None:
        self._chat_service = InboxChatService(store)

    def send_message(
        self,
        user_id: str,
        organization_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        user_token: Optional[str] = None,
        onboarding: bool = False,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        return self._chat_service.send_message(
            user_id=user_id,
            organization_id=organization_id,
            message=message,
            conversation_id=conversation_id,
            user_token=user_token,
            onboarding=onboarding,
            file_references=file_references,
        )
