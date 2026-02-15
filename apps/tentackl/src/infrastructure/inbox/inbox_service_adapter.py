"""Infrastructure adapters for inbox operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.inbox.ports import InboxOperationsPort
from src.infrastructure.inbox.inbox_service import InboxService


class InboxServiceAdapter(InboxOperationsPort):
    """Adapter exposing InboxService through the InboxOperationsPort."""

    def __init__(self, inbox_service: InboxService) -> None:
        self._service = inbox_service

    async def get_unread_count(self, user_id: str) -> int:
        return await self._service.get_unread_count(user_id)

    async def get_attention_count(self, user_id: str) -> int:
        return await self._service.get_attention_count(user_id)

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
        return await self._service.list_inbox(
            user_id=user_id,
            read_status=read_status,
            priority=priority,
            search_text=search_text,
            exclude_archived=exclude_archived,
            limit=limit,
            offset=offset,
        )

    async def bulk_update_status(self, conversation_ids: List[str], read_status: str) -> int:
        return await self._service.bulk_update_status(
            conversation_ids=conversation_ids,
            read_status=read_status,
        )

    async def update_status(self, conversation_id: str, read_status: str) -> bool:
        return await self._service.update_status(conversation_id, read_status)

    async def get_thread(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self._service.get_thread(conversation_id)

    async def create_follow_up(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        follow_up_text: str,
    ) -> Dict[str, Any]:
        return await self._service.create_follow_up(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            follow_up_text=follow_up_text,
        )
