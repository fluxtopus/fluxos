"""Domain ports for inbox operations."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional, Protocol


class InboxOperationsPort(Protocol):
    """Port for inbox operations."""

    async def get_unread_count(self, user_id: str) -> int:
        ...

    async def get_attention_count(self, user_id: str) -> int:
        ...

    async def list_inbox(
        self,
        user_id: str,
        read_status: Optional[str],
        priority: Optional[str],
        search_text: Optional[str],
        exclude_archived: bool,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        ...

    async def bulk_update_status(self, conversation_ids: List[str], read_status: str) -> int:
        ...

    async def update_status(self, conversation_id: str, read_status: str) -> bool:
        ...

    async def get_thread(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def create_follow_up(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        follow_up_text: str,
    ) -> Dict[str, Any]:
        ...


class ConversationStorePort(Protocol):
    """Port for conversation ownership checks."""

    async def get_conversation_user_id(self, conversation_id: str) -> Optional[str]:
        ...


class InboxChatPort(Protocol):
    """Port for inbox chat streaming."""

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
        ...


class InboxEventStreamPort(Protocol):
    """Port for inbox event streaming."""

    def stream_events(self, user_id: str) -> AsyncGenerator[str, None]:
        ...


class FileUsagePort(Protocol):
    """Port for checking whether a file is referenced by active tasks."""

    async def check_file_usage(
        self,
        organization_id: str,
        file_id: str,
    ) -> Dict[str, Any]:
        ...
