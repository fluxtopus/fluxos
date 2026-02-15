"""World state builder for Arrow system prompt.

Builds dynamic context showing:
- Active tasks and their status
- Pending checkpoints awaiting approval
- Recently completed tasks

This gives the LLM awareness of what's happening in the user's world.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


async def build_world_state(
    user_id: str,
    delegation_service: Any,
    include_completed: bool = True,
    completed_limit: int = 5,
) -> str:
    """Build world state section for Arrow system prompt.

    Args:
        user_id: The user's ID
        delegation_service: DelegationService instance
        include_completed: Include recently completed tasks
        completed_limit: Max completed tasks to include

    Returns:
        Formatted world state string for system prompt
    """
    if not delegation_service:
        return ""

    try:
        from src.domain.tasks.models import TaskStatus, StepStatus

        # Get active tasks
        all_plans = await delegation_service.get_user_plans(
            user_id=user_id,
            status=None,
            limit=50,
        )

        # Categorize plans
        active_statuses = {
            TaskStatus.PLANNING,
            TaskStatus.READY,
            TaskStatus.EXECUTING,
            TaskStatus.CHECKPOINT,
        }

        active_tasks = [p for p in all_plans if p.status in active_statuses]
        completed_tasks = []
        failed_tasks = []

        if include_completed:
            completed_tasks = [
                p for p in all_plans if p.status == TaskStatus.COMPLETED
            ][:completed_limit]
            failed_tasks = [
                p for p in all_plans
                if p.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
            ][:3]

        # Get pending checkpoints
        checkpoints = await delegation_service.get_pending_checkpoints(user_id)

        # Build the world state string
        sections = []

        # Active Tasks Section
        if active_tasks:
            active_section = "## Active Tasks\n"
            for task in active_tasks:
                progress = task.get_progress_percentage()
                status_emoji = _get_status_emoji(task.status)
                active_section += f"- {status_emoji} **{task.goal[:60]}{'...' if len(task.goal) > 60 else ''}**\n"
                active_section += f"  - ID: `{task.id}`\n"
                status_value = task.status.value if hasattr(task.status, "value") else str(task.status)
                completed_steps = [
                    s for s in task.steps
                    if getattr(s, "status", None) == StepStatus.DONE
                    or getattr(s, "status", None) == StepStatus.SKIPPED
                ]
                active_section += f"  - Status: {status_value} ({progress:.0f}% complete)\n"
                active_section += f"  - Steps: {len(completed_steps)}/{len(task.steps)}\n"
            sections.append(active_section)
        else:
            sections.append("## Active Tasks\n_No active tasks_\n")

        # Pending Checkpoints Section (Critical - needs immediate attention)
        if checkpoints:
            checkpoint_section = "## ⚠️ Pending Checkpoints (Need Approval)\n"
            for cp in checkpoints:
                checkpoint_section += f"- **{cp.checkpoint_name}**: {cp.description[:50]}...\n"
                checkpoint_section += f"  - Plan ID: `{cp.plan_id}`\n"
                checkpoint_section += f"  - Step ID: `{cp.step_id}`\n"
                if cp.expires_at:
                    expires_in = (cp.expires_at - datetime.utcnow()).total_seconds() / 60
                    if expires_in > 0:
                        checkpoint_section += f"  - Expires in: {expires_in:.0f} minutes\n"
                    else:
                        checkpoint_section += f"  - ⚠️ EXPIRED\n"
                if cp.preview_data:
                    # Include key preview data
                    preview_items = []
                    for k, v in list(cp.preview_data.items())[:3]:
                        if isinstance(v, str) and len(v) > 50:
                            v = v[:50] + "..."
                        preview_items.append(f"{k}: {v}")
                    if preview_items:
                        checkpoint_section += f"  - Preview: {', '.join(preview_items)}\n"
            sections.append(checkpoint_section)

        # Recently Completed Section
        if completed_tasks:
            completed_section = "## Recently Completed\n"
            for task in completed_tasks:
                completed_section += f"- ✅ {task.goal[:60]}{'...' if len(task.goal) > 60 else ''}\n"
                if task.completed_at:
                    completed_section += f"  - Completed: {_format_relative_time(task.completed_at)}\n"
            sections.append(completed_section)

        # Failed Tasks Section (if any)
        if failed_tasks:
            failed_section = "## Failed Tasks\n"
            for task in failed_tasks:
                failed_section += f"- ❌ {task.goal[:60]}{'...' if len(task.goal) > 60 else ''}\n"
                # Find error message from failed steps
                for step in task.steps:
                    if step.error_message:
                        failed_section += f"  - Error: {step.error_message[:50]}...\n"
                        break
            sections.append(failed_section)

        # Combine sections
        if sections:
            world_state = "# Current World State\n\n"
            world_state += "\n".join(sections)
            world_state += "\n---\n"
            return world_state

        return ""

    except Exception as e:
        logger.error("Failed to build world state", error=str(e))
        return ""


def _get_status_emoji(status) -> str:
    """Get emoji for plan status."""
    status_value = status.value if hasattr(status, 'value') else str(status)
    emoji_map = {
        "ready": "🟢",
        "executing": "🔄",
        "checkpoint": "⏸️",
        "replanning": "🔧",
        "completed": "✅",
        "failed": "❌",
        "paused": "⏸️",
    }
    return emoji_map.get(status_value, "⚪")


def _format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time string."""
    if not dt:
        return "unknown"

    now = datetime.utcnow()
    diff = now - dt

    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600}h ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60}m ago"
    else:
        return "just now"


async def build_similar_tasks_context(
    user_message: str,
    user_id: str,
    organization_id: str,
    task_embedding_service: Any,
    limit: int = 3,
) -> str:
    """Build similar tasks context for Arrow system prompt.

    Uses embeddings to find similar past tasks and inject them as context.

    Args:
        user_message: The user's current message
        user_id: The user's ID
        organization_id: Organization ID
        task_embedding_service: TaskEmbeddingService instance
        limit: Max similar tasks to return

    Returns:
        Formatted similar tasks string for system prompt
    """
    if not task_embedding_service:
        return ""

    try:
        # Find similar tasks
        similar_tasks = await task_embedding_service.find_similar_tasks(
            query=user_message,
            organization_id=organization_id,
            limit=limit,
        )

        if not similar_tasks:
            return ""

        # Build context
        context = "# Similar Past Tasks\n\n"
        context += "These are similar tasks that were completed previously. You can use them as reference:\n\n"

        for task in similar_tasks:
            context += f"## {task.get('goal', 'Unknown goal')[:60]}\n"
            context += f"- Similarity: {task.get('similarity', 0):.0%}\n"

            # Include step summary
            if task.get('steps'):
                context += "- Steps: " + ", ".join(
                    s.get('name', 'step') for s in task['steps'][:5]
                )
                if len(task['steps']) > 5:
                    context += f" (+{len(task['steps']) - 5} more)"
                context += "\n"

            # Include any useful outputs
            if task.get('outputs'):
                context += f"- Outputs: {', '.join(task['outputs'].keys())}\n"

            context += "\n"

        context += "---\n"
        return context

    except Exception as e:
        logger.error("Failed to build similar tasks context", error=str(e))
        return ""
