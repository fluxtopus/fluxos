# REVIEW: ConversationStore defines its own data structures and performs
# REVIEW: persistence in one class, with multiple commits per operation and
# REVIEW: disabled data masking. Consider splitting DTOs from storage and
# REVIEW: using transactions to keep conversation/message/metrics consistent.
"""PostgreSQL implementation of ConversationStore interface."""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import uuid
import re
from decimal import Decimal
from sqlalchemy import select, update, and_, or_, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
import structlog

from src.interfaces.database import Database
from src.database.models import (
    Conversation, Message, ConversationMetrics,
    ConversationStatus, TriggerType, MessageType, MessageDirection,
    ReadStatus, InboxPriority
)
from src.database.task_models import Task

logger = structlog.get_logger()


class ConversationTrigger:
    """Conversation trigger information."""
    def __init__(self, type: TriggerType, source: str, details: Dict[str, Any], conversation_source: str = "task"):
        self.type = type
        self.source = source
        self.details = details
        self.conversation_source = conversation_source  # "arrow" or "task"


class MessageContent:
    """Structured message content."""
    def __init__(self, role: str, text: Optional[str] = None, 
                 data: Optional[Dict[str, Any]] = None,
                 tool_calls: Optional[List[Dict[str, Any]]] = None,
                 masked_fields: Optional[List[str]] = None):
        self.role = role
        self.text = text
        self.data = data
        self.tool_calls = tool_calls
        self.masked_fields = masked_fields or []


class MessageMetadata:
    """Message metadata."""
    def __init__(self, model: Optional[str] = None, temperature: Optional[float] = None,
                 tokens: Optional[Dict[str, int]] = None, latency_ms: Optional[int] = None,
                 error: Optional[str] = None, retry_count: int = 0):
        self.model = model
        self.temperature = temperature
        self.tokens = tokens  # {"prompt": N, "completion": N, "total": N}
        self.latency_ms = latency_ms
        self.error = error
        self.retry_count = retry_count


class Cost:
    """Cost information."""
    def __init__(self, amount: float, currency: str = "USD"):
        self.amount = amount
        self.currency = currency


class MessageData:
    """Complete message data structure."""
    def __init__(self, agent_id: str, message_type: MessageType, 
                 direction: MessageDirection, content: MessageContent,
                 metadata: MessageMetadata, cost: Optional[Cost] = None,
                 parent_message_id: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.timestamp = datetime.utcnow()
        self.message_type = message_type
        self.direction = direction
        self.content = content
        self.metadata = metadata
        self.parent_message_id = parent_message_id
        self.cost = cost


class ConversationView:
    """View of a conversation with messages."""
    def __init__(self, conversation: Conversation, messages: List[Message]):
        self.conversation = conversation
        self.messages = messages


class ConversationCosts:
    """Aggregated costs for a conversation."""
    def __init__(self, total_cost: float, cost_by_agent: Dict[str, float],
                 cost_by_model: Dict[str, float], token_usage: Dict[str, int]):
        self.total_cost = total_cost
        self.cost_by_agent = cost_by_agent
        self.cost_by_model = cost_by_model
        self.token_usage = token_usage


class ConversationQuery:
    """Query parameters for searching conversations."""
    def __init__(self, workflow_id: Optional[str] = None, 
                 agent_id: Optional[str] = None,
                 status: Optional[ConversationStatus] = None,
                 start_time: Optional[datetime] = None,
                 end_time: Optional[datetime] = None,
                 tags: Optional[List[str]] = None,
                 limit: int = 100,
                 offset: int = 0):
        self.workflow_id = workflow_id
        self.agent_id = agent_id
        self.status = status
        self.start_time = start_time
        self.end_time = end_time
        self.tags = tags
        self.limit = limit
        self.offset = offset


class DataMasker:
    """Mask sensitive data before storage."""
    
    patterns = {
        'api_key': r'sk-[a-zA-Z0-9]+',
        'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        'phone': r'\+?1?\d{10,14}',
        'ssn': r'\d{3}-\d{2}-\d{4}',
        'credit_card': r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}'
    }
    
    def mask(self, content: str) -> Tuple[str, List[str]]:
        """Mask sensitive content and return masked fields."""
        masked_content = content
        masked_fields = []
        
        for field_type, pattern in self.patterns.items():
            if re.search(pattern, content):
                masked_content = re.sub(pattern, f'[{field_type.upper()}_MASKED]', masked_content)
                masked_fields.append(field_type)
        
        return masked_content, masked_fields


class ConversationStore:
    """PostgreSQL implementation of conversation storage."""
    
    def __init__(self, database: Database):
        self.db = database
        self.masker = DataMasker()
        
    async def start_conversation(
        self,
        workflow_id: str,
        root_agent_id: str,
        trigger: ConversationTrigger,
        parent_conversation_id: Optional[str] = None
    ) -> Conversation:
        """Start a new conversation."""
        async with self.db.get_session() as session:
            conversation = Conversation(
                workflow_id=uuid.UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id,
                root_agent_id=root_agent_id,
                trigger_type=trigger.type,
                trigger_source=trigger.source,
                trigger_details=trigger.details,
                parent_conversation_id=uuid.UUID(parent_conversation_id) if parent_conversation_id else None,
                status=ConversationStatus.ACTIVE,
                source=trigger.conversation_source
            )
            
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            
            # Create metrics entry
            metrics = ConversationMetrics(
                conversation_id=conversation.id,
                total_messages=0,
                total_llm_calls=0,
                total_tool_calls=0,
                total_errors=0,
                total_tokens=0,
                total_cost=Decimal('0.0'),
                average_latency_ms=0.0,
                max_latency_ms=0
            )
            
            session.add(metrics)
            await session.commit()
            
            logger.info("Started new conversation", 
                       conversation_id=str(conversation.id),
                       workflow_id=workflow_id,
                       root_agent_id=root_agent_id)
            
            return conversation
    
    async def add_message(
        self,
        conversation_id: str,
        message_data: MessageData
    ) -> bool:
        """Add a message to a conversation."""
        async with self.db.get_session() as session:
            # NOTE: Data masking disabled - it was destructively replacing
            # user content (emails, phones) making features like "add contact"
            # impossible. See PR for details.
            # if message_data.content.text:
            #     masked_text, masked_fields = self.masker.mask(message_data.content.text)
            #     message_data.content.text = masked_text
            #     message_data.content.masked_fields.extend(masked_fields)
            
            # Create message
            message = Message(
                id=uuid.UUID(message_data.id),
                conversation_id=uuid.UUID(conversation_id),
                agent_id=message_data.agent_id,
                timestamp=message_data.timestamp,
                message_type=message_data.message_type,
                direction=message_data.direction,
                role=message_data.content.role,
                content_text=message_data.content.text,
                content_data=message_data.content.data,
                tool_calls=message_data.content.tool_calls,
                masked_fields=message_data.content.masked_fields,
                model=message_data.metadata.model,
                temperature=message_data.metadata.temperature,
                prompt_tokens=message_data.metadata.tokens.get('prompt_tokens', message_data.metadata.tokens.get('prompt')) if message_data.metadata.tokens else None,
                completion_tokens=message_data.metadata.tokens.get('completion_tokens', message_data.metadata.tokens.get('completion')) if message_data.metadata.tokens else None,
                total_tokens=message_data.metadata.tokens.get('total_tokens', message_data.metadata.tokens.get('total')) if message_data.metadata.tokens else None,
                latency_ms=message_data.metadata.latency_ms,
                cost_amount=Decimal(str(message_data.cost.amount)) if message_data.cost else None,
                cost_currency=message_data.cost.currency if message_data.cost else None,
                error=message_data.metadata.error,
                retry_count=message_data.metadata.retry_count,
                parent_message_id=uuid.UUID(message_data.parent_message_id) if message_data.parent_message_id else None
            )
            
            session.add(message)
            
            # Update metrics
            await self._update_metrics(session, conversation_id, message_data)
            
            await session.commit()
            
            logger.debug("Added message to conversation",
                        conversation_id=conversation_id,
                        message_id=str(message.id),
                        message_type=message_data.message_type.value)
            
            return True
    
    async def end_conversation(
        self,
        conversation_id: str,
        status: ConversationStatus
    ) -> bool:
        """Mark conversation as ended."""
        async with self.db.get_session() as session:
            result = await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(status=status, end_time=datetime.utcnow())
            )
            
            await session.commit()
            
            logger.info("Ended conversation",
                       conversation_id=conversation_id,
                       status=status.value)
            
            return result.rowcount > 0
    
    async def get_conversation(
        self,
        conversation_id: str,
        include_messages: bool = True
    ) -> Optional[ConversationView]:
        """Retrieve a conversation."""
        async with self.db.get_session() as session:
            query = select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            
            if include_messages:
                query = query.options(selectinload(Conversation.messages))
            
            result = await session.execute(query)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
            
            return ConversationView(
                conversation=conversation,
                messages=conversation.messages if include_messages else []
            )
    
    async def search_conversations(
        self,
        query: ConversationQuery
    ) -> List[Conversation]:
        """Search conversations."""
        async with self.db.get_session() as session:
            stmt = select(Conversation)
            
            conditions = []
            
            if query.workflow_id:
                conditions.append(Conversation.workflow_id == uuid.UUID(query.workflow_id))
            
            if query.status:
                conditions.append(Conversation.status == query.status)
            
            if query.start_time:
                conditions.append(Conversation.start_time >= query.start_time)
            
            if query.end_time:
                conditions.append(Conversation.start_time <= query.end_time)
            
            if query.tags:
                conditions.append(Conversation.tags.contains(query.tags))
            
            if conditions:
                stmt = stmt.where(and_(*conditions))
            
            stmt = stmt.limit(query.limit).offset(query.offset)
            stmt = stmt.order_by(Conversation.start_time.desc())
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_conversation_costs(
        self,
        conversation_id: str
    ) -> ConversationCosts:
        """Calculate total costs for a conversation."""
        async with self.db.get_session() as session:
            # Get aggregated costs
            result = await session.execute(
                select(
                    func.sum(Message.cost_amount).label('total_cost'),
                    func.sum(Message.total_tokens).label('total_tokens')
                )
                .where(Message.conversation_id == uuid.UUID(conversation_id))
            )
            
            row = result.one()
            total_cost = float(row.total_cost or 0)
            total_tokens = row.total_tokens or 0
            
            # Cost by agent
            agent_costs_result = await session.execute(
                select(
                    Message.agent_id,
                    func.sum(Message.cost_amount).label('agent_cost')
                )
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .group_by(Message.agent_id)
            )
            
            cost_by_agent = {
                row.agent_id: float(row.agent_cost or 0)
                for row in agent_costs_result
            }
            
            # Cost by model
            model_costs_result = await session.execute(
                select(
                    Message.model,
                    func.sum(Message.cost_amount).label('model_cost')
                )
                .where(
                    and_(
                        Message.conversation_id == uuid.UUID(conversation_id),
                        Message.model.isnot(None)
                    )
                )
                .group_by(Message.model)
            )
            
            cost_by_model = {
                row.model: float(row.model_cost or 0)
                for row in model_costs_result
            }
            
            # Token usage by type
            token_usage = {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': total_tokens
            }
            
            token_result = await session.execute(
                select(
                    func.sum(Message.prompt_tokens).label('prompt_tokens'),
                    func.sum(Message.completion_tokens).label('completion_tokens')
                )
                .where(Message.conversation_id == uuid.UUID(conversation_id))
            )
            
            token_row = token_result.one()
            token_usage['prompt_tokens'] = token_row.prompt_tokens or 0
            token_usage['completion_tokens'] = token_row.completion_tokens or 0
            
            return ConversationCosts(
                total_cost=total_cost,
                cost_by_agent=cost_by_agent,
                cost_by_model=cost_by_model,
                token_usage=token_usage
            )
    
    async def _update_metrics(self, session: AsyncSession, conversation_id: str, message_data: MessageData):
        """Update conversation metrics."""
        # Get existing metrics
        result = await session.execute(
            select(ConversationMetrics)
            .where(ConversationMetrics.conversation_id == uuid.UUID(conversation_id))
        )
        
        metrics = result.scalar_one_or_none()
        
        if metrics:
            metrics.total_messages += 1
            
            # Count one LLM call per prompt/response pair by incrementing on response only
            if message_data.message_type == MessageType.LLM_RESPONSE:
                metrics.total_llm_calls += 1
            
            if message_data.message_type == MessageType.TOOL_CALL:
                metrics.total_tool_calls += 1
            
            if message_data.message_type == MessageType.ERROR:
                metrics.total_errors += 1
            
            if message_data.metadata.tokens:
                tks = message_data.metadata.tokens
                total = tks.get('total_tokens', tks.get('total', 0))
                metrics.total_tokens += total or 0
            
            if message_data.cost:
                metrics.total_cost += Decimal(str(message_data.cost.amount))
            
            if message_data.metadata.latency_ms:
                # Update average latency
                if metrics.average_latency_ms > 0:
                    metrics.average_latency_ms = (
                        (metrics.average_latency_ms * (metrics.total_messages - 1) + message_data.metadata.latency_ms) 
                        / metrics.total_messages
                    )
                else:
                    metrics.average_latency_ms = float(message_data.metadata.latency_ms)
                
                # Update max latency
                if message_data.metadata.latency_ms > metrics.max_latency_ms:
                    metrics.max_latency_ms = message_data.metadata.latency_ms
            
            metrics.updated_at = datetime.utcnow()

    async def _get_or_create_metrics(self, conversation_id):
        """Get existing metrics or create a new row for the conversation.

        This helper exists to support tests that verify metrics updates.
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(ConversationMetrics).where(ConversationMetrics.conversation_id == uuid.UUID(str(conversation_id)))
            )
            metrics = result.scalar_one_or_none()
            if metrics:
                return metrics
            # Create metrics row
            metrics = ConversationMetrics(
                conversation_id=uuid.UUID(str(conversation_id)),
                total_messages=0,
                total_llm_calls=0,
                total_tool_calls=0,
                total_errors=0,
                total_tokens=0,
                total_cost=Decimal("0.0"),
                average_latency_ms=0.0,
                max_latency_ms=0,
            )
            session.add(metrics)
            await session.commit()
            return metrics

    async def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        """List conversations ordered by creation date (newest first)."""
        async with self.db.get_session() as session:
            stmt = select(Conversation).order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_messages(self, conversation_id: str) -> List[Message]:
        """Get all messages for a conversation."""
        async with self.db.get_session() as session:
            stmt = select(Message).where(
                Message.conversation_id == uuid.UUID(conversation_id)
            ).order_by(Message.timestamp.asc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ---- Inbox Query Methods ----

    async def get_inbox_conversations(
        self,
        user_id: str,
        read_status: Optional[ReadStatus] = None,
        priority: Optional[InboxPriority] = None,
        search_text: Optional[str] = None,
        exclude_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """Query inbox conversations for a user with last message and task data.

        Returns conversations WHERE user_id matches and read_status IS NOT NULL,
        optionally filtered by read_status, priority, and search text.
        Each result includes the latest assistant message and linked task information.
        """
        async with self.db.get_session() as session:
            # Subquery: latest assistant message per conversation
            latest_msg_sq = (
                select(
                    Message.conversation_id,
                    Message.content_text,
                    Message.timestamp,
                )
                .where(Message.role == "assistant")
                .order_by(Message.conversation_id, Message.timestamp.desc())
                .distinct(Message.conversation_id)
                .subquery("latest_msg")
            )

            # Subquery: first user message per conversation (used as title for inbox-source)
            first_user_msg_sq = (
                select(
                    Message.conversation_id,
                    Message.content_text,
                )
                .where(Message.role == "user")
                .order_by(Message.conversation_id, Message.timestamp.asc())
                .distinct(Message.conversation_id)
                .subquery("first_user_msg")
            )

            # Subquery: latest task per conversation (avoid duplicates when
            # multiple tasks reference the same conversation_id).
            latest_task_sq = (
                select(
                    Task.conversation_id,
                    Task.goal,
                    Task.status,
                    Task.id,
                )
                .order_by(Task.conversation_id, Task.created_at.desc())
                .distinct(Task.conversation_id)
                .subquery("latest_task")
            )

            # Build main query
            stmt = (
                select(
                    Conversation.id.label("conversation_id"),
                    Conversation.read_status,
                    Conversation.priority,
                    Conversation.root_agent_id,
                    latest_msg_sq.c.content_text.label("last_message_text"),
                    latest_msg_sq.c.timestamp.label("last_message_at"),
                    first_user_msg_sq.c.content_text.label("first_user_message"),
                    latest_task_sq.c.goal.label("task_goal"),
                    latest_task_sq.c.status.label("task_status"),
                    latest_task_sq.c.id.label("task_id"),
                )
                .outerjoin(
                    latest_msg_sq,
                    Conversation.id == latest_msg_sq.c.conversation_id,
                )
                .outerjoin(
                    first_user_msg_sq,
                    Conversation.id == first_user_msg_sq.c.conversation_id,
                )
                .outerjoin(
                    latest_task_sq,
                    latest_task_sq.c.conversation_id == Conversation.id,
                )
                .where(
                    and_(
                        Conversation.user_id == user_id,
                        Conversation.read_status.isnot(None),
                    )
                )
            )

            if read_status is not None:
                stmt = stmt.where(Conversation.read_status == read_status)
            if priority is not None:
                stmt = stmt.where(Conversation.priority == priority)
            if exclude_archived:
                stmt = stmt.where(Conversation.read_status != ReadStatus.ARCHIVED)
            if search_text:
                pattern = f"%{search_text}%"
                # Search across ALL messages in the conversation
                msg_match = (
                    select(Message.id)
                    .where(
                        and_(
                            Message.conversation_id == Conversation.id,
                            Message.content_text.ilike(pattern),
                        )
                    )
                    .correlate(Conversation)
                    .exists()
                )
                stmt = stmt.where(msg_match)

            stmt = stmt.order_by(latest_msg_sq.c.timestamp.desc().nullslast())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "conversation_id": str(row.conversation_id),
                    "read_status": row.read_status.value if row.read_status else None,
                    "priority": row.priority.value if row.priority else None,
                    "source": "inbox" if row.root_agent_id == "inbox_chat" else "task",
                    "last_message_text": row.last_message_text,
                    "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                    "task_goal": row.task_goal,
                    "task_status": row.task_status,
                    "task_id": str(row.task_id) if row.task_id else None,
                    "title": row.task_goal or (row.first_user_message[:100] if row.first_user_message else None),
                }
                for row in rows
            ]

    async def get_unread_count(self, user_id: str) -> int:
        """Count unread inbox conversations for a user."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.user_id == user_id,
                        Conversation.read_status == ReadStatus.UNREAD,
                    )
                )
            )
            return result.scalar_one()

    async def get_attention_count(self, user_id: str) -> int:
        """Count inbox conversations needing attention for a user.

        Only counts conversations that are both priority=ATTENTION and
        read_status=UNREAD (i.e. not yet seen by the user).
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.user_id == user_id,
                        Conversation.priority == InboxPriority.ATTENTION,
                        Conversation.read_status == ReadStatus.UNREAD,
                    )
                )
            )
            return result.scalar_one()

    async def update_read_status(
        self, conversation_id: str, read_status: ReadStatus
    ) -> bool:
        """Update read_status on a single conversation."""
        async with self.db.get_session() as session:
            result = await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(read_status=read_status)
            )
            await session.commit()
            return result.rowcount > 0

    async def bulk_update_read_status(
        self, conversation_ids: List[str], read_status: ReadStatus
    ) -> int:
        """Update read_status on multiple conversations. Returns count updated."""
        if not conversation_ids:
            return 0
        uuids = [uuid.UUID(cid) for cid in conversation_ids]
        async with self.db.get_session() as session:
            result = await session.execute(
                update(Conversation)
                .where(Conversation.id.in_(uuids))
                .values(read_status=read_status)
            )
            await session.commit()
            return result.rowcount

    async def get_conversation_user_id(self, conversation_id: str) -> Optional[str]:
        """Return the user_id of a conversation, or None if not found."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Conversation.user_id).where(
                    Conversation.id == uuid.UUID(conversation_id)
                )
            )
            row = result.one_or_none()
            return row[0] if row else None

    async def set_conversation_user_id(self, conversation_id: str, user_id: str) -> None:
        """Assign a user_id to a conversation."""
        async with self.db.get_session() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(user_id=user_id)
            )
            await session.commit()

    async def set_inbox_fields(
        self,
        conversation_id: str,
        user_id: str,
        read_status: ReadStatus,
        priority: InboxPriority,
    ) -> None:
        """Assign inbox-specific fields on a conversation."""
        async with self.db.get_session() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(
                    user_id=user_id,
                    read_status=read_status,
                    priority=priority,
                )
            )
            await session.commit()

    async def get_inbox_thread(self, conversation_id: str) -> Optional[dict]:
        """Get conversation with all messages and associated task data.

        Returns conversation details, all messages (ordered by timestamp ASC),
        and the linked task's goal, status, steps, and accumulated_findings.
        """
        async with self.db.get_session() as session:
            # Load conversation with messages eagerly
            conv_result = await session.execute(
                select(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .options(selectinload(Conversation.messages))
            )
            conversation = conv_result.scalar_one_or_none()
            if not conversation:
                return None

            # Load all associated tasks (supports multi-task conversations)
            tasks_result = await session.execute(
                select(Task).where(Task.conversation_id == uuid.UUID(conversation_id))
            )
            tasks = list(tasks_result.scalars().all())
            primary_task = tasks[0] if tasks else None

            # Sort messages by timestamp ASC
            messages = sorted(conversation.messages, key=lambda m: m.timestamp)

            def _task_dict(t):
                return {
                    "id": str(t.id),
                    "goal": t.goal,
                    "status": t.status,
                    "steps": t.steps or [],
                    "accumulated_findings": t.accumulated_findings or [],
                }

            source = "inbox" if conversation.root_agent_id == "inbox_chat" else "task"

            return {
                "conversation_id": str(conversation.id),
                "read_status": conversation.read_status.value if conversation.read_status else None,
                "priority": conversation.priority.value if conversation.priority else None,
                "source": source,
                "task": _task_dict(primary_task) if primary_task else None,
                "tasks": [_task_dict(t) for t in tasks],
                "messages": [
                    {
                        "id": str(msg.id),
                        "role": msg.role,
                        "content_text": msg.content_text,
                        "content_data": msg.content_data,
                        "message_type": msg.message_type.value if msg.message_type else None,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "agent_id": msg.agent_id if hasattr(msg, 'agent_id') else None,
                    }
                    for msg in messages
                ],
            }
