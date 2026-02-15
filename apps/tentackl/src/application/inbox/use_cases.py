"""Application use cases for inbox operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.domain.inbox.ports import (
    ConversationStorePort,
    FileUsagePort,
    InboxChatPort,
    InboxEventStreamPort,
    InboxOperationsPort,
)


class InboxConversationNotFound(Exception):
    """Raised when an inbox conversation does not exist."""


class InboxConversationForbidden(Exception):
    """Raised when a user accesses a conversation they do not own."""


class InboxChatUnavailable(Exception):
    """Raised when inbox chat dependencies are not configured."""


class InboxEventStreamUnavailable(Exception):
    """Raised when inbox event-stream dependencies are not configured."""


@dataclass
class InboxUseCases:
    """Application-layer orchestration for inbox operations.

    This layer should coordinate domain logic and repositories, but for now
    it delegates to InboxService/ConversationStore to preserve behavior
    during migration.
    """

    inbox_ops: InboxOperationsPort
    conversation_store: ConversationStorePort
    chat_ops: Optional[InboxChatPort] = None
    event_stream_ops: Optional[InboxEventStreamPort] = None
    file_usage_ops: Optional[FileUsagePort] = None

    async def get_unread_count(self, user_id: str) -> int:
        return await self.inbox_ops.get_unread_count(user_id)

    async def get_attention_count(self, user_id: str) -> int:
        return await self.inbox_ops.get_attention_count(user_id)

    async def list_inbox(
        self,
        user_id: str,
        read_status: Optional[str] = None,
        priority: Optional[str] = None,
        search_text: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        exclude_archived = read_status is None
        effective_read_status = read_status
        if priority == "attention" and read_status is None:
            effective_read_status = "unread"

        return await self.inbox_ops.list_inbox(
            user_id=user_id,
            read_status=effective_read_status,
            priority=priority,
            search_text=search_text,
            exclude_archived=exclude_archived,
            limit=limit,
            offset=offset,
        )

    async def bulk_update_status(
        self,
        conversation_ids: List[str],
        read_status: str,
    ) -> int:
        return await self.inbox_ops.bulk_update_status(
            conversation_ids=conversation_ids,
            read_status=read_status,
        )

    async def update_status(
        self,
        user_id: str,
        conversation_id: str,
        read_status: str,
    ) -> bool:
        await self._assert_ownership(user_id, conversation_id)
        updated = await self.inbox_ops.update_status(
            conversation_id=conversation_id,
            read_status=read_status,
        )
        if not updated:
            raise InboxConversationNotFound()
        return updated

    async def get_thread(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        await self._assert_ownership(user_id, conversation_id)
        thread = await self.inbox_ops.get_thread(conversation_id)
        if thread is None:
            raise InboxConversationNotFound()
        return thread

    async def create_follow_up(
        self,
        user_id: str,
        organization_id: str,
        conversation_id: str,
        follow_up_text: str,
    ) -> Dict[str, Any]:
        await self._assert_ownership(user_id, conversation_id)
        return await self.inbox_ops.create_follow_up(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            follow_up_text=follow_up_text,
        )

    async def assert_conversation_access(self, user_id: str, conversation_id: str) -> None:
        """Validate conversation ownership without performing an operation."""
        await self._assert_ownership(user_id, conversation_id)

    def stream_chat(
        self,
        user_id: str,
        organization_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        user_token: Optional[str] = None,
        onboarding: bool = False,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        if self.chat_ops is None:
            raise InboxChatUnavailable("Inbox chat adapter is not configured")
        return self.chat_ops.send_message(
            user_id=user_id,
            organization_id=organization_id,
            message=message,
            conversation_id=conversation_id,
            user_token=user_token,
            onboarding=onboarding,
            file_references=file_references,
        )

    def stream_events(self, user_id: str) -> AsyncGenerator[str, None]:
        if self.event_stream_ops is None:
            raise InboxEventStreamUnavailable("Inbox event stream adapter is not configured")
        return self.event_stream_ops.stream_events(user_id)

    async def check_file_usage(
        self,
        organization_id: str,
        file_id: str,
    ) -> Dict[str, Any]:
        """Check if a file is referenced by any active task."""
        if self.file_usage_ops is None:
            return {"in_use": False, "tasks": []}
        return await self.file_usage_ops.check_file_usage(organization_id, file_id)

    async def _assert_ownership(self, user_id: str, conversation_id: str) -> None:
        owner_id = await self.conversation_store.get_conversation_user_id(conversation_id)
        if owner_id is None:
            raise InboxConversationNotFound()
        if owner_id != user_id:
            raise InboxConversationForbidden()
