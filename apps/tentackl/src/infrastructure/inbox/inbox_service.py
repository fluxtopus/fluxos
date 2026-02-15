# REVIEW: InboxService still coordinates follow-up creation directly.
# REVIEW: Consider moving follow-up orchestration into an Inbox application
# REVIEW: use case to keep the service focused on data access.
"""
Inbox Service — core service layer for the Agent Inbox feature.

The API router delegates to this service for all inbox operations:
listing, filtering, status updates, thread retrieval, and follow-up
task creation.
"""

from typing import List, Optional
import uuid as _uuid

import structlog

from src.database.conversation_store import (
    ConversationStore,
    ConversationTrigger,
)
from src.database.models import (
    ConversationStatus,
    InboxPriority,
    ReadStatus,
    TriggerType,
)
from src.infrastructure.inbox.summary_service import SummaryGenerationService
from src.application.tasks import TaskUseCases
from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases

logger = structlog.get_logger(__name__)


class InboxService:
    """Main service for inbox operations.

    Wraps ConversationStore inbox queries with validation,
    pagination metadata, and follow-up task creation.
    """

    def __init__(
        self,
        conversation_store: ConversationStore,
        summary_service: Optional[SummaryGenerationService] = None,
        task_use_cases: Optional[TaskUseCases] = None,
    ) -> None:
        self._store = conversation_store
        self._summary_service = summary_service or SummaryGenerationService()
        self._task_use_cases = task_use_cases

    async def _get_task_use_cases(self) -> TaskUseCases:
        if self._task_use_cases is None:
            self._task_use_cases = await provider_get_task_use_cases()
        return self._task_use_cases

    # ------------------------------------------------------------------
    # List / Count
    # ------------------------------------------------------------------

    async def list_inbox(
        self,
        user_id: str,
        read_status: Optional[str] = None,
        priority: Optional[str] = None,
        search_text: Optional[str] = None,
        exclude_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Return paginated inbox items for *user_id*.

        Args:
            user_id: Owner of the inbox.
            read_status: Optional filter (``unread``, ``read``, ``archived``).
            priority: Optional filter (``normal``, ``attention``).
            search_text: Optional text to search in task goals (ILIKE).
            exclude_archived: When True, exclude archived conversations.
            limit: Max items per page.
            offset: Pagination offset.

        Returns:
            ``{"items": [...], "total": int, "limit": int, "offset": int}``
        """
        rs_enum: Optional[ReadStatus] = None
        if read_status is not None:
            rs_enum = ReadStatus(read_status)

        pri_enum: Optional[InboxPriority] = None
        if priority is not None:
            pri_enum = InboxPriority(priority)

        items = await self._store.get_inbox_conversations(
            user_id=user_id,
            read_status=rs_enum,
            priority=pri_enum,
            search_text=search_text,
            exclude_archived=exclude_archived,
            limit=limit,
            offset=offset,
        )

        # Total count (separate query without pagination for accurate total)
        total = len(items)
        if total == limit:
            # Might be more — get the real count
            total = await self._store.get_inbox_count(
                user_id=user_id,
                read_status=rs_enum,
                priority=pri_enum,
                search_text=search_text,
                exclude_archived=exclude_archived,
            ) if hasattr(self._store, "get_inbox_count") else total

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_unread_count(self, user_id: str) -> int:
        """Return the number of unread inbox conversations."""
        return await self._store.get_unread_count(user_id)

    async def get_attention_count(self, user_id: str) -> int:
        """Return the number of inbox conversations needing attention."""
        return await self._store.get_attention_count(user_id)

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    async def update_status(
        self, conversation_id: str, read_status: str
    ) -> bool:
        """Validate and update read_status on a single conversation.

        Args:
            conversation_id: UUID string of the conversation.
            read_status: New status (``unread``, ``read``, ``archived``).

        Returns:
            ``True`` if the row was updated, ``False`` if not found.

        Raises:
            ValueError: If *read_status* is not a valid enum value.
        """
        rs_enum = ReadStatus(read_status)  # raises ValueError on bad input
        return await self._store.update_read_status(conversation_id, rs_enum)

    async def bulk_update_status(
        self, conversation_ids: List[str], read_status: str
    ) -> int:
        """Bulk-update read_status on multiple conversations.

        Returns:
            Count of rows updated.

        Raises:
            ValueError: If *read_status* is not a valid enum value.
        """
        rs_enum = ReadStatus(read_status)
        return await self._store.bulk_update_read_status(conversation_ids, rs_enum)

    # ------------------------------------------------------------------
    # Thread
    # ------------------------------------------------------------------

    async def get_thread(self, conversation_id: str) -> Optional[dict]:
        """Return the full thread (conversation + messages + task data)."""
        return await self._store.get_inbox_thread(conversation_id)

    # ------------------------------------------------------------------
    # Follow-up
    # ------------------------------------------------------------------

    async def create_follow_up(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        follow_up_text: str,
    ) -> dict:
        """Create a follow-up task linked to the original conversation.

        Finds the original task via *conversation_id*, creates a new task
        with *follow_up_text* as goal and ``parent_task_id`` set to the
        original task, and creates a new conversation for the follow-up
        with ``parent_conversation_id`` linking back.

        Returns:
            ``{"task_id": str, "conversation_id": str, "goal": str, "status": str}``

        Raises:
            ValueError: If the original conversation or task is not found.
        """
        # Load the original thread to find its linked task
        thread = await self._store.get_inbox_thread(conversation_id)
        if thread is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        original_task = thread.get("task")
        if original_task is None:
            raise ValueError(
                f"No task linked to conversation {conversation_id}"
            )

        original_task_id = original_task["id"]

        # Create a new conversation for the follow-up
        new_conv = await self._store.start_conversation(
            workflow_id=str(_uuid.uuid4()),
            root_agent_id="task_orchestrator",
            trigger=ConversationTrigger(
                type=TriggerType.MANUAL,
                source="inbox_follow_up",
                details={
                    "parent_conversation_id": conversation_id,
                    "parent_task_id": original_task_id,
                },
                conversation_source="task",
            ),
            parent_conversation_id=conversation_id,
        )

        # Set inbox fields on the new conversation
        await self._store.update_read_status(
            str(new_conv.id), ReadStatus.UNREAD
        )

        task_use_cases = await self._get_task_use_cases()
        new_task = await task_use_cases.create_task(
            user_id=user_id,
            organization_id=organization_id,
            goal=follow_up_text,
            constraints={},
            metadata={
                "parent_task_id": original_task_id,
                "parent_conversation_id": conversation_id,
                "source": "inbox_follow_up",
            },
            auto_start=True,
        )
        await task_use_cases.set_parent_task(
            task_id=new_task.id,
            parent_task_id=original_task_id,
        )
        await task_use_cases.link_conversation(
            task_id=new_task.id,
            conversation_id=str(new_conv.id),
        )
        await self._store.set_conversation_user_id(str(new_conv.id), user_id)

        logger.info(
            "Follow-up task created",
            original_conversation_id=conversation_id,
            original_task_id=original_task_id,
            new_task_id=new_task.id,
            new_conversation_id=str(new_conv.id),
            goal=follow_up_text[:100],
        )

        return {
            "task_id": new_task.id,
            "conversation_id": str(new_conv.id),
            "goal": follow_up_text,
            "status": "planning",
        }
