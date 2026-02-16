# REVIEW: InboxChatService blends conversation persistence, prompt building,
# REVIEW: tool execution, and SSE streaming, making the service large and hard
# REVIEW: to test. Consider extracting chat orchestration from transport (SSE)
# REVIEW: and moving prompt construction into application-layer use cases.
# REVIEW: This makes the service large and hard to test. Consider extracting
# REVIEW: DB updates into ConversationStore (or a repository), and separate
# REVIEW: chat orchestration from transport (SSE) concerns.
"""
Inbox Chat Service — Flux, the conversational agent for the inbox.

Reuses Arrow's proven tool-calling infrastructure (BaseTool, ToolRegistry,
ToolExecutor, handle_arrow_chat_with_tools, OpenRouter LLM client) but
with its own system prompt, tool set, and conversation persistence.

Usage:
    service = InboxChatService(conversation_store)
    async for event in service.send_message(user_id, org_id, "Hello"):
        print(event)  # SSE-formatted strings
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
import structlog

from src.core.config import settings
from src.infrastructure.flux_runtime.chat_handler import handle_flux_chat_with_tools
from src.infrastructure.flux_runtime.tool_executor import ToolExecutor
from src.infrastructure.flux_runtime.world_state import build_world_state
from src.database.conversation_store import (
    ConversationStore,
    ConversationTrigger,
    MessageContent,
    MessageData,
    MessageMetadata,
)
from src.database.models import (
    InboxPriority,
    MessageDirection,
    MessageType,
    ReadStatus,
    TriggerType,
)
from src.application.tasks import TaskUseCases
from src.application.checkpoints import CheckpointUseCases
from src.application.tasks.providers import (
    get_task_use_cases as provider_get_task_use_cases,
    get_checkpoint_use_cases as provider_get_checkpoint_use_cases,
)
from src.infrastructure.inbox.inbox_tool_registry import get_inbox_tool_registry

logger = structlog.get_logger(__name__)

# System prompt template path
_PROMPT_DIR = Path(__file__).parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPT_DIR / "inbox_system_prompt.md"
_ONBOARDING_PROMPT_PATH = _PROMPT_DIR / "onboarding_prompt.md"

_task_use_cases: Optional[TaskUseCases] = None
_checkpoint_use_cases: Optional[CheckpointUseCases] = None


async def _get_task_use_cases() -> TaskUseCases:
    global _task_use_cases
    if _task_use_cases is None:
        _task_use_cases = await provider_get_task_use_cases()
    return _task_use_cases


async def _get_checkpoint_use_cases() -> CheckpointUseCases:
    global _checkpoint_use_cases
    if _checkpoint_use_cases is None:
        _checkpoint_use_cases = await provider_get_checkpoint_use_cases()
    return _checkpoint_use_cases


class InboxChatService:
    """Conversational agent for the inbox.

    Orchestrates the chat loop:
    1. Create or load conversation
    2. Save user message
    3. Build system prompt with world state
    4. Call LLM via Arrow's chat handler (with tool calling)
    5. Stream SSE events
    6. Persist assistant response
    7. Publish inbox SSE notification
    """

    def __init__(self, conversation_store: ConversationStore) -> None:
        self._store = conversation_store
        self._registry = get_inbox_tool_registry()
        self._tool_executor = ToolExecutor(registry=self._registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message(
        self,
        user_id: str,
        organization_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        user_token: Optional[str] = None,
        onboarding: bool = False,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a chat response.

        Yields SSE-formatted strings:
            data: {"status": "thinking"}
            data: {"status": "tool_execution", "tool": "create_task"}
            data: {"content": "I've started a task to..."}
            data: {"conversation_id": "uuid-123"}
            data: {"done": true}

        Args:
            user_id: Authenticated user ID.
            organization_id: User's organization.
            message: User message text.
            conversation_id: Existing conversation to continue, or None for new.
            user_token: JWT token for authenticated tool calls (e.g. integrations).
        """
        # 1. Create or load conversation
        conv_id = conversation_id
        is_new = conv_id is None

        if is_new:
            conv = await self._create_conversation(user_id)
            conv_id = str(conv.id)

        # Emit conversation_id early so frontend can track it
        yield _sse({"conversation_id": conv_id})

        # 2. Save user message
        await self._save_user_message(conv_id, message)

        # 3. Emit "thinking" status
        yield _sse({"status": "thinking"})

        # 4. Load conversation history
        history = await self._load_history(conv_id)

        # 5. Build system prompt
        system_prompt = await self._build_system_prompt(
            user_id=user_id,
            conversation_id=conv_id,
            onboarding=onboarding,
            file_references=file_references,
        )

        # 6. Build tool context
        tool_context: Dict[str, Any] = {
            "user_id": user_id,
            "organization_id": organization_id,
            "conversation_id": conv_id,
        }
        if user_token:
            tool_context["user_token"] = user_token
        if file_references:
            tool_context["file_references"] = file_references

        # 7. Call LLM with tool calling
        try:
            chat_result = await handle_flux_chat_with_tools(
                system_prompt=system_prompt,
                user_message=message,
                conversation_history=history,
                tool_executor=self._tool_executor,
                call_llm_func=_call_openrouter_llm,
                workflow_context=tool_context,
                max_tool_rounds=5,
            )
        except Exception as e:
            logger.error("Inbox chat LLM call failed", error=str(e))
            yield _sse({"error": f"Chat failed: {str(e)}"})
            yield _sse({"done": True})
            return

        # 8. Extract and emit tool execution info
        for tc in chat_result.get("tool_calls_made", []):
            yield _sse({
                "status": "tool_execution",
                "tool": tc.get("tool"),
            })

        # 9. Emit the response content
        response_text = chat_result.get("response", "")
        if response_text:
            yield _sse({"content": response_text})

        # 10. Save assistant message(s) to conversation
        await self._save_assistant_messages(conv_id, chat_result)

        # 11. Publish inbox SSE event for real-time updates
        await self._publish_inbox_event(user_id, conv_id, response_text)

        # 12. Done
        yield _sse({"done": True})

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    async def _create_conversation(self, user_id: str):
        """Create a new inbox conversation."""
        conv = await self._store.start_conversation(
            workflow_id=str(uuid.uuid4()),
            root_agent_id="inbox_chat",
            trigger=ConversationTrigger(
                type=TriggerType.MANUAL,
                source="inbox_chat",
                details={},
                conversation_source="inbox",
            ),
        )

        # Set user_id and inbox fields
        await self._store.set_inbox_fields(
            conversation_id=str(conv.id),
            user_id=user_id,
            read_status=ReadStatus.READ,
            priority=InboxPriority.NORMAL,
        )

        logger.info("Created inbox conversation", conversation_id=str(conv.id))
        return conv

    async def _save_user_message(self, conversation_id: str, text: str) -> None:
        """Persist the user's message."""
        msg = MessageData(
            agent_id="inbox_chat",
            message_type=MessageType.LLM_PROMPT,
            direction=MessageDirection.INBOUND,
            content=MessageContent(role="user", text=text),
            metadata=MessageMetadata(),
        )
        await self._store.add_message(conversation_id, msg)

    async def _save_assistant_messages(
        self, conversation_id: str, chat_result: Dict[str, Any]
    ) -> None:
        """Persist the assistant response (and tool call info)."""
        response_text = chat_result.get("response", "")
        tool_calls_made = chat_result.get("tool_calls_made", [])

        # Save tool call messages for context
        for tc in tool_calls_made:
            tool_msg = MessageData(
                agent_id="inbox_chat",
                message_type=MessageType.TOOL_CALL,
                direction=MessageDirection.OUTBOUND,
                content=MessageContent(
                    role="assistant",
                    text=f"Used tool: {tc.get('tool')}",
                    data={
                        "tool": tc.get("tool"),
                        "arguments": tc.get("arguments"),
                        "result": tc.get("result"),
                        "source": "inbox_chat",
                    },
                ),
                metadata=MessageMetadata(),
            )
            await self._store.add_message(conversation_id, tool_msg)

        # Save final assistant response
        if response_text:
            assistant_msg = MessageData(
                agent_id="inbox_chat",
                message_type=MessageType.LLM_RESPONSE,
                direction=MessageDirection.OUTBOUND,
                content=MessageContent(
                    role="assistant",
                    text=response_text,
                    data={"source": "inbox_chat"},
                ),
                metadata=MessageMetadata(),
            )
            await self._store.add_message(conversation_id, assistant_msg)

    # ------------------------------------------------------------------
    # History loading
    # ------------------------------------------------------------------

    async def _load_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Load conversation history for LLM context.

        Returns messages in OpenRouter format. Applies a sliding window
        of the last 50 messages to prevent exceeding token limits.

        For task step messages, appends step output data so the LLM can
        reference actual results (not just "Step — done.").
        """
        messages = await self._store.get_messages(conversation_id)

        # Sliding window — keep last 50 messages
        if len(messages) > 50:
            messages = messages[-50:]

        history: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.role or "assistant"
            content = msg.content_text or ""

            # Skip empty messages
            if not content.strip():
                continue

            # Enrich task step messages with their output data
            if msg.content_data and msg.agent_id == "task_orchestrator":
                outputs = msg.content_data.get("outputs")
                if outputs:
                    # Truncate large outputs to avoid blowing up context
                    import json

                    try:
                        outputs_str = json.dumps(outputs, default=str)
                        if len(outputs_str) > 2000:
                            outputs_str = outputs_str[:2000] + "… (truncated)"
                        content += f"\n\nStep output:\n```json\n{outputs_str}\n```"
                    except (TypeError, ValueError):
                        pass

            history.append({"role": role, "content": content})

        return history

    # ------------------------------------------------------------------
    # System prompt builder
    # ------------------------------------------------------------------

    async def _build_system_prompt(
        self,
        user_id: str,
        conversation_id: str,
        onboarding: bool = False,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build the system prompt with world state and tool catalog."""
        # Load template
        template = _SYSTEM_PROMPT_PATH.read_text()

        # Tool catalog
        tool_defs = self._registry.get_tool_definitions()
        tools_text = ""
        for td in tool_defs:
            func = td.get("function", {})
            tools_text += f"- **{func.get('name')}**: {func.get('description', '')}\n"

        # World state (active tasks, checkpoints, completions)
        world_state = ""
        try:
            task_use_cases = await _get_task_use_cases()
            checkpoint_use_cases = await _get_checkpoint_use_cases()

            class _WorldStateDelegate:
                def __init__(self, task_cases: TaskUseCases, checkpoint_cases: CheckpointUseCases) -> None:
                    self._task_cases = task_cases
                    self._checkpoint_cases = checkpoint_cases

                async def get_user_plans(self, user_id: str, status=None, limit: int = 50):
                    return await self._task_cases.list_tasks(
                        user_id=user_id,
                        status=status,
                        limit=limit,
                    )

                async def get_pending_checkpoints(self, user_id: str):
                    return await self._checkpoint_cases.list_pending(user_id)

            world_state = await build_world_state(
                user_id=user_id,
                delegation_service=_WorldStateDelegate(task_use_cases, checkpoint_use_cases),
            )
        except Exception as e:
            logger.warning("Failed to build world state for inbox", error=str(e))

        # Conversation-specific task context
        conversation_tasks = await self._get_conversation_tasks(conversation_id)

        # Replace placeholders
        prompt = template.replace("{{TOOLS_CATALOG}}", tools_text)
        prompt = prompt.replace("{{WORLD_STATE}}", world_state)
        prompt = prompt.replace("{{CONVERSATION_TASKS}}", conversation_tasks)

        # Append file references section if present
        if file_references:
            prompt += "\n\n" + self._build_file_references_section(file_references)

        # Append onboarding instructions for first-time users
        if onboarding:
            prompt += "\n\n" + _ONBOARDING_PROMPT_PATH.read_text()

        return prompt

    @staticmethod
    def _build_file_references_section(file_references: List[Dict[str, Any]]) -> str:
        """Build the system prompt section describing available file references.

        Replicates the pattern from dynamic_prompt_builder so the LLM knows
        which files the user attached and how to access them.
        """
        lines = [
            "## Available File References",
            "",
            "The user has referenced the following files from their storage. "
            "These files are available for use:",
            "",
        ]

        for ref in file_references:
            file_id = ref.get("id", "unknown")
            name = ref.get("name", "unknown")
            path = ref.get("path", "/")
            content_type = ref.get("content_type", "unknown")
            lines.append(
                f"- **{name}** (id: `{file_id}`, type: `{content_type}`, path: `{path}`)"
            )

        lines.extend([
            "",
            "**How to use these files:**",
            "- When creating a task that needs these files, include them in the task goal",
            "- Reference files by their id for tool operations",
            "- The user expects you to acknowledge and use these referenced files",
            "",
        ])

        return "\n".join(lines)

    async def _get_conversation_tasks(self, conversation_id: str) -> str:
        """Build a detailed summary of tasks linked to this conversation.

        Includes step-by-step outputs and accumulated findings so the
        LLM can reference actual task results in follow-up answers.
        """
        try:
            import json as _json

            thread = await self._store.get_inbox_thread(conversation_id)
            tasks = thread.get("tasks") if thread else None

            if not tasks:
                return "_No tasks in this conversation yet._"

            sections = []
            for t in tasks:
                steps = t.get("steps") if isinstance(t, dict) else []
                completed = sum(
                    1
                    for s in steps
                    if isinstance(s, dict) and s.get("status") in {"completed", "done"}
                )

                header = (
                    f"### {(t.get('goal') or '')[:80]}\n"
                    f"- **Status**: {t.get('status')} | **Steps**: {completed}/{len(steps)} | **ID**: `{t.get('id')}`"
                )

                # Include step outputs for completed steps
                step_lines = []
                for s in steps:
                    if not isinstance(s, dict):
                        continue
                    s_name = s.get("name", "step")
                    s_status = s.get("status", "unknown")
                    s_outputs = s.get("outputs")

                    if s_status == "completed" and s_outputs:
                        try:
                            out_str = _json.dumps(s_outputs, default=str)
                            if len(out_str) > 1000:
                                out_str = out_str[:1000] + "…"
                            step_lines.append(f"- **{s_name}** ✅: `{out_str}`")
                        except (TypeError, ValueError):
                            step_lines.append(f"- **{s_name}** ✅")
                    elif s_status == "failed":
                        err = s.get("error_message", "unknown error")
                        step_lines.append(f"- **{s_name}** ❌: {err[:200]}")
                    elif s_status in ("running", "pending"):
                        step_lines.append(f"- **{s_name}** ⏳ {s_status}")

                # Include accumulated findings
                findings = t.get("accumulated_findings") or []
                finding_lines = []
                if findings:
                    for f in findings[-5:]:  # Last 5 findings
                        if isinstance(f, dict):
                            f_text = f.get("summary") or f.get("content") or str(f)
                        else:
                            f_text = str(f)
                        if len(f_text) > 300:
                            f_text = f_text[:300] + "…"
                        finding_lines.append(f"  - {f_text}")

                section = header
                if step_lines:
                    section += "\n\n**Steps:**\n" + "\n".join(step_lines)
                if finding_lines:
                    section += "\n\n**Findings:**\n" + "\n".join(finding_lines)
                sections.append(section)

            return "\n\n".join(sections)

        except Exception as e:
            logger.warning("Failed to get conversation tasks", error=str(e))
            return "_Could not load tasks._"

    # ------------------------------------------------------------------
    # Event publishing
    # ------------------------------------------------------------------

    async def _publish_inbox_event(
        self, user_id: str, conversation_id: str, preview: str
    ) -> None:
        """Publish an inbox SSE event so the frontend updates in real time."""
        try:
            from src.infrastructure.tasks.event_publisher import get_task_event_publisher

            publisher = get_task_event_publisher()
            await publisher.inbox_message_created(
                user_id=user_id,
                conversation_id=conversation_id,
                message_preview=preview[:100] if preview else "",
                priority="normal",
            )
        except Exception as e:
            logger.warning("Failed to publish inbox event", error=str(e))


# ======================================================================
# LLM Client (reuses Arrow's pattern)
# ======================================================================


async def _call_openrouter_llm(
    system_prompt: str,
    user_message: Optional[str] = None,
    conversation_history: List[Any] = None,
    tools: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Call OpenRouter API using the model registry.

    Uses ModelSelector.for_inbox_chat() to resolve the model routing for Flux
    (primary model + fallbacks + provider preferences).

    Returns: {"message": str, "tool_calls": list, "finish_reason": str}
    """
    from src.llm.model_selector import ModelSelector

    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not configured. "
            "Set OPENROUTER_API_KEY in the tentacle service environment."
        )

    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history:
            if isinstance(msg, dict):
                if msg.get("role") == "tool":
                    messages.append(msg)
                elif msg.get("tool_calls"):
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                        "tool_calls": msg["tool_calls"],
                    })
                else:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            else:
                messages.append({"role": msg.role, "content": msg.content})

    if user_message:
        messages.append({"role": "user", "content": user_message})

    # Resolve model routing from the registry
    routing = ModelSelector.for_inbox_chat()

    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": 0.3,
    }

    # Apply routing: single model or fallback array
    if len(routing.models) == 1:
        payload["model"] = routing.models[0]
    else:
        payload["models"] = routing.models

    # Apply provider routing preferences
    if routing.provider:
        provider_dict = routing.provider.to_dict()
        if provider_dict:
            payload["provider"] = provider_dict

    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        message_data = data["choices"][0]["message"]
        finish_reason = data["choices"][0].get("finish_reason", "stop")

        return {
            "message": message_data.get("content", ""),
            "tool_calls": message_data.get("tool_calls", []),
            "finish_reason": finish_reason,
        }


# ======================================================================
# SSE formatting helper
# ======================================================================


def _sse(data: Any) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"
