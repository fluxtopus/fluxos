"""
# REVIEW:
# - Uses module-level conversation_store and lazy InboxService singleton; no explicit lifecycle management.
API routes for the Agent Inbox.

Provides endpoints for:
- Listing inbox conversations (with filters)
- Getting unread count
- Updating read status (single and bulk)
- Getting full conversation thread
- Creating follow-up tasks
- Real-time inbox events via SSE
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.params import Depends as DependsParam
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.application.inbox import (
    InboxChatUnavailable,
    InboxUseCases,
    InboxConversationForbidden,
    InboxConversationNotFound,
    InboxEventStreamUnavailable,
)
from src.infrastructure.inbox.use_case_factory import (
    build_inbox_use_cases,
    get_or_create_inbox_service,
)

router = APIRouter(prefix="/api/inbox", tags=["inbox"])

# Service instances (set by app.py at startup)
conversation_store: Optional[Any] = None


def _get_inbox_service():
    """Lazily initialise and return the InboxService singleton."""
    if conversation_store is None:
        raise RuntimeError("conversation_store not initialised for inbox router")
    return get_or_create_inbox_service(conversation_store)


def _get_conversation_store():
    """Get the ConversationStore instance for inbox routes."""
    if conversation_store is None:
        raise RuntimeError("conversation_store not initialised for inbox router")
    return conversation_store


def get_inbox_use_cases(
    service=Depends(_get_inbox_service),
    store=Depends(_get_conversation_store),
) -> InboxUseCases:
    """Provide application-layer inbox use cases."""
    return build_inbox_use_cases(store=store, service=service)


def _resolve_inbox_use_cases(use_cases: InboxUseCases) -> InboxUseCases:
    """Resolve use cases for direct (non-FastAPI) calls in tests."""
    if isinstance(use_cases, DependsParam):
        service = _get_inbox_service()
        store = _get_conversation_store()
        return build_inbox_use_cases(store=store, service=service)
    return use_cases


# --- Request models ---

class StatusUpdateRequest(BaseModel):
    read_status: str


class BulkStatusUpdateRequest(BaseModel):
    conversation_ids: List[str]
    read_status: str


class FollowUpRequest(BaseModel):
    text: str


class InboxChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    onboarding: bool = False
    file_references: Optional[List[Dict[str, Any]]] = None


# === Inbox Endpoints ===


@router.get("/unread-count")
async def get_unread_count(
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Return the number of unread inbox conversations for the current user."""
    resolved_use_cases = _resolve_inbox_use_cases(use_cases)
    count = await resolved_use_cases.get_unread_count(user.id)
    return {"count": count}


@router.get("/attention-count")
async def get_attention_count(
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Return the number of inbox conversations needing attention."""
    resolved_use_cases = _resolve_inbox_use_cases(use_cases)
    count = await resolved_use_cases.get_attention_count(user.id)
    return {"count": count}


@router.patch("/bulk")
async def bulk_update_status(
    body: BulkStatusUpdateRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Bulk-update read_status on multiple conversations.

    Returns the count of conversations updated.
    """
    try:
        resolved_use_cases = _resolve_inbox_use_cases(use_cases)
        updated = await resolved_use_cases.bulk_update_status(
            conversation_ids=body.conversation_ids,
            read_status=body.read_status,
        )
        return {"updated": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


@router.post("/chat/stream")
async def inbox_chat_stream(
    body: InboxChatRequest,
    request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Stream a conversational chat response via SSE.

    Creates or continues a conversation. Flux processes the
    message using tool calling (task creation, status checks, etc.)
    and streams the response as Server-Sent Events.

    SSE event format:
        data: {"conversation_id": "uuid"}
        data: {"status": "thinking"}
        data: {"status": "tool_execution", "tool": "create_task"}
        data: {"content": "I've started a task to..."}
        data: {"done": true}
    """
    resolved_use_cases = _resolve_inbox_use_cases(use_cases)

    # Ownership check for existing conversations
    if body.conversation_id:
        try:
            await resolved_use_cases.assert_conversation_access(
                user_id=user.id,
                conversation_id=body.conversation_id,
            )
        except InboxConversationNotFound:
            raise HTTPException(status_code=404, detail="Conversation not found")
        except InboxConversationForbidden:
            raise HTTPException(status_code=403, detail="Not your conversation")

    org_id = user.metadata.get("organization_id") if user.metadata else None

    # Extract bearer token for tools that need authenticated Mimic calls
    user_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        user_token = auth_header[7:]

    try:
        return StreamingResponse(
            resolved_use_cases.stream_chat(
                user_id=user.id,
                organization_id=org_id or "",
                message=body.message,
                conversation_id=body.conversation_id,
                user_token=user_token,
                onboarding=body.onboarding,
                file_references=body.file_references,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except InboxChatUnavailable:
        raise HTTPException(status_code=503, detail="Inbox chat service not initialized")


@router.get("/events")
async def inbox_events(
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """
    Server-Sent Events stream for real-time inbox updates.

    Subscribes to the authenticated user's inbox event stream
    inbox events and forwards them as SSE. Sends a heartbeat ping every
    30 seconds to keep the connection alive.

    Event types:
        - inbox.message.created: A new message was added to an inbox conversation
        - inbox.status.updated: An inbox conversation's read status changed
        - heartbeat: Keep-alive ping (every 30 seconds)
    """
    resolved_use_cases = _resolve_inbox_use_cases(use_cases)
    try:
        return StreamingResponse(
            resolved_use_cases.stream_events(user.id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except InboxEventStreamUnavailable:
        raise HTTPException(status_code=503, detail="Inbox event stream service not initialized")


@router.get("")
async def list_inbox(
    read_status: Optional[str] = Query(
        None, description="Filter: unread, read, archived"
    ),
    priority: Optional[str] = Query(
        None, description="Filter: normal, attention"
    ),
    q: Optional[str] = Query(
        None, description="Search text to filter by task goal or message content"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """List inbox conversations for the authenticated user.

    Returns a paginated list of inbox items with the latest message preview,
    associated task goal/status, and read/priority indicators.
    """
    try:
        resolved_use_cases = _resolve_inbox_use_cases(use_cases)
        result = await resolved_use_cases.list_inbox(
            user_id=user.id,
            read_status=read_status,
            priority=priority,
            search_text=q,
            limit=limit,
            offset=offset,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


@router.patch("/{conversation_id}")
async def update_status(
    conversation_id: str,
    body: StatusUpdateRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Update read_status of a single inbox conversation.

    Validates that the conversation exists and belongs to the authenticated user.
    Returns 404 if not found, 403 if wrong user.
    """
    try:
        resolved_use_cases = _resolve_inbox_use_cases(use_cases)
        await resolved_use_cases.update_status(
            user_id=user.id,
            conversation_id=conversation_id,
            read_status=body.read_status,
        )
        return {
            "success": True,
            "conversation_id": conversation_id,
            "read_status": body.read_status,
        }
    except InboxConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except InboxConversationForbidden:
        raise HTTPException(status_code=403, detail="Not your conversation")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


@router.get("/{conversation_id}/thread")
async def get_thread(
    conversation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Get the full conversation thread with all messages and task data.

    Returns the conversation metadata, associated task (goal, status, steps,
    accumulated_findings), and all messages sorted by timestamp ASC.
    Validates ownership — returns 404 if not found, 403 if wrong user.
    """
    try:
        resolved_use_cases = _resolve_inbox_use_cases(use_cases)
        thread = await resolved_use_cases.get_thread(
            user_id=user.id,
            conversation_id=conversation_id,
        )
        return thread
    except InboxConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except InboxConversationForbidden:
        raise HTTPException(status_code=403, detail="Not your conversation")


@router.post("/{conversation_id}/follow-up")
async def create_follow_up(
    conversation_id: str,
    body: FollowUpRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Create a follow-up task linked to the original conversation.

    The follow-up text becomes the new task's goal. The new task is linked
    to the original via parent_task_id, and a new conversation is created
    with parent_conversation_id pointing back.

    Returns the new task data: task_id, conversation_id, goal, status.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None

    try:
        resolved_use_cases = _resolve_inbox_use_cases(use_cases)
        result = await resolved_use_cases.create_follow_up(
            user_id=user.id,
            organization_id=org_id or "",
            conversation_id=conversation_id,
            follow_up_text=body.text,
        )
        return result
    except InboxConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except InboxConversationForbidden:
        raise HTTPException(status_code=403, detail="Not your conversation")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


# === File Usage Check ===


@router.get("/files/check-usage/{file_id}")
async def check_file_usage(
    file_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("inbox", "view")),
    use_cases: InboxUseCases = Depends(get_inbox_use_cases),
):
    """Check if a file is referenced by any active task.

    Used by the file explorer to prevent deletion of in-use files.
    """
    resolved_use_cases = _resolve_inbox_use_cases(use_cases)
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        return {"in_use": False, "tasks": []}
    return await resolved_use_cases.check_file_usage(org_id, file_id)
