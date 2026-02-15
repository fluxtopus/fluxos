"""Factory helpers for inbox use case composition."""

from __future__ import annotations

from typing import Any, Optional

from src.application.inbox import InboxUseCases
from src.infrastructure.inbox.conversation_store_adapter import ConversationStoreAdapter
from src.infrastructure.inbox.file_usage_adapter import FileUsageAdapter
from src.infrastructure.inbox.inbox_chat_adapter import InboxChatServiceAdapter
from src.infrastructure.inbox.inbox_event_stream_adapter import InboxEventStreamAdapter
from src.infrastructure.inbox.inbox_service_adapter import InboxServiceAdapter
from src.infrastructure.inbox.inbox_service import InboxService

_inbox_service: Optional[InboxService] = None


def get_or_create_inbox_service(store: Any) -> InboxService:
    """Return a singleton InboxService bound to the provided store."""
    global _inbox_service
    if _inbox_service is None:
        _inbox_service = InboxService(store)
    return _inbox_service


def reset_inbox_service() -> None:
    """Reset singleton service (useful for tests/startup rewiring)."""
    global _inbox_service
    _inbox_service = None


def build_inbox_use_cases(
    store: Any,
    service: Optional[Any] = None,
) -> InboxUseCases:
    """Build InboxUseCases with all required adapters."""
    resolved_service = service or get_or_create_inbox_service(store)
    return InboxUseCases(
        inbox_ops=InboxServiceAdapter(resolved_service),
        conversation_store=ConversationStoreAdapter(store),
        chat_ops=InboxChatServiceAdapter(store),
        event_stream_ops=InboxEventStreamAdapter(),
        file_usage_ops=FileUsageAdapter(),
    )
