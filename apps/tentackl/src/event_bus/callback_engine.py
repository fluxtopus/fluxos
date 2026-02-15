"""Callback Engine implementation for executing event-triggered actions."""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog
import time

from src.interfaces.event_bus import (
    CallbackEngineInterface, Callback, CallbackAction, CallbackResult,
    Event, EventSourceType
)
from src.agents.factory import AgentFactory
from src.agents.configurable_agent import (
    ConfigurableAgent,
    AgentConfig,
    ExecutionStrategy,
    CapabilityConfig,
    StateSchema,
)
from src.interfaces.configurable_agent import ResourceConstraints
from src.interfaces.sub_agent_generator import AgentType
from src.interfaces.state_store import StateStoreInterface
from src.interfaces.budget_controller import BudgetControllerInterface
from src.core.config import settings
import redis.asyncio as redis

logger = structlog.get_logger()


@dataclass
class CallbackExecution:
    """Track callback execution for rate limiting."""
    callback_id: str
    timestamp: datetime
    success: bool


class CallbackEngine(CallbackEngineInterface):
    """
    Callback Engine for executing event-triggered actions.
    
    This component:
    - Executes callback actions (spawn agents, update state, etc.)
    - Enforces constraints (rate limits, concurrency)
    - Tracks execution metrics
    - Integrates with budget control
    """
    
    def __init__(
        self,
        state_store: Optional[StateStoreInterface] = None,
        budget_controller: Optional[BudgetControllerInterface] = None,
        redis_url: Optional[str] = None,
        key_prefix: str = "tentackl:callback"
    ):
        self._state_store = state_store
        self._budget_controller = budget_controller
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        self._key_prefix = key_prefix
        self._executions: Dict[str, List[CallbackExecution]] = {}
        self._active_executions: Dict[str, int] = {}  # callback_id -> count
        self._initialized = False
        
    async def initialize(self):
        """Initialize the callback engine."""
        if self._initialized:
            return
            
        # Initialize Redis connection
        self._redis_client = await redis.from_url(
            self._redis_url,
            decode_responses=True
        )
        
        # Register default agents if using factory (check if not already registered)
        from src.agents.registry import register_default_agents
        from src.agents.factory import AgentFactory
        try:
            registered = set(AgentFactory.get_registered_types())
        except Exception:
            registered = set()
        if 'worker' not in registered:
            try:
                register_default_agents()
            except Exception:
                # If already registered concurrently, ignore
                pass
        
        self._initialized = True
        logger.info("Callback Engine initialized")
    
    async def execute_callback(self, callback: Callback, event: Event) -> CallbackResult:
        """Execute a callback action."""
        await self._ensure_initialized()
        
        start_time = time.time()
        results = []
        errors = []
        
        try:
            # Check constraints
            ok, constraint_error = await self.validate_constraints(callback)
            if not ok:
                return CallbackResult(
                    callback_id=callback.id,
                    success=False,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    errors=[constraint_error or "Callback constraints not met"]
                )
            
            # Check trigger condition
            if callback.trigger.condition and not self._evaluate_condition(
                callback.trigger.condition, event
            ):
                return CallbackResult(
                    callback_id=callback.id,
                    success=False,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    errors=["Trigger condition not met"]
                )
            
            # Track active execution
            self._active_executions[callback.id] = self._active_executions.get(callback.id, 0) + 1
            
            try:
                # Execute each action
                for action in callback.actions:
                    try:
                        result = await self._execute_action(action, event, callback)
                        results.append(result)
                    except Exception as e:
                        error_msg = f"Action {action.action_type} failed: {str(e)}"
                        logger.error(error_msg, callback_id=callback.id, action=action.action_type)
                        errors.append(error_msg)
                        # Continue with other actions unless configured to stop on error
                        if action.config.get('stop_on_error', False):
                            break
                
                # Record execution
                execution = CallbackExecution(
                    callback_id=callback.id,
                    timestamp=datetime.utcnow(),
                    success=len(errors) == 0
                )
                await self._record_execution(execution)
                
                # Update metrics
                await self._update_metrics(callback.id, execution)
                
                return CallbackResult(
                    callback_id=callback.id,
                    success=len(errors) == 0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    results=results,
                    errors=errors
                )
                
            finally:
                # Decrement active execution count
                self._active_executions[callback.id] = max(0, self._active_executions.get(callback.id, 1) - 1)
                
        except Exception as e:
            logger.error(f"Callback execution failed: {e}", callback_id=callback.id)
            return CallbackResult(
                callback_id=callback.id,
                success=False,
                execution_time_ms=(time.time() - start_time) * 1000,
                errors=[str(e)]
            )
    
    async def validate_constraints(self, callback: Callback) -> (bool, Optional[str]):
        """Check if callback constraints allow execution."""
        await self._ensure_initialized()
        
        constraints = callback.constraints
        
        # Check rate limit
        if constraints.rate_limit_calls and constraints.rate_limit_window:
            if not await self._check_rate_limit(
                callback.id,
                constraints.rate_limit_calls,
                constraints.rate_limit_window
            ):
                logger.warning(
                    "Rate limit exceeded",
                    callback_id=callback.id,
                    limit=constraints.rate_limit_calls,
                    window=constraints.rate_limit_window
                )
                return False, "constraints not met: Rate limit exceeded"
        
        # Check concurrency limit
        if constraints.max_parallel:
            current_active = self._active_executions.get(callback.id, 0)
            if current_active >= constraints.max_parallel:
                logger.warning(
                    "Concurrency limit exceeded",
                    callback_id=callback.id,
                    limit=constraints.max_parallel,
                    current=current_active
                )
                return False, "constraints not met: Concurrency limit exceeded"
        
        # Check budget if configured
        if self._budget_controller and 'budget_key' in callback.trigger.__dict__:
            # Would check budget constraints here
            pass
        
        return True, None
    
    async def get_callback_metrics(self, callback_id: str) -> Dict[str, Any]:
        """Get execution metrics for a callback."""
        await self._ensure_initialized()
        
        metrics_key = f"{self._key_prefix}:metrics:{callback_id}"
        metrics = await self._redis_client.hgetall(metrics_key)
        
        if not metrics:
            return {
                'total_executions': 0,
                'successful_executions': 0,
                'failed_executions': 0,
                'avg_execution_time_ms': 0,
                'last_execution': None
            }
        
        return {
            'total_executions': int(metrics.get('total_executions', 0)),
            'successful_executions': int(metrics.get('successful_executions', 0)),
            'failed_executions': int(metrics.get('failed_executions', 0)),
            'avg_execution_time_ms': float(metrics.get('avg_execution_time_ms', 0)),
            'last_execution': metrics.get('last_execution')
        }
    
    async def _execute_action(self, action: CallbackAction, event: Event, callback: Callback) -> Dict[str, Any]:
        """Execute a single callback action."""
        action_type = action.action_type
        config = action.config
        
        # Optional conditional execution: config.when using a small JSONLogic subset
        try:
            condition = config.get('when') if isinstance(config, dict) else None
        except Exception:
            condition = None
        if condition is not None:
            # Build evaluation context from event
            try:
                ctx = {"event": {"type": event.event_type, "data": event.data or {}}, "state": {}}
                if not self._evaluate_condition(condition, ctx):
                    return {
                        'action': action_type,
                        'skipped': True,
                        'reason': 'condition_false',
                        'when': condition
                    }
            except Exception as e:
                logger.warning("Failed to evaluate condition for action; proceeding", error=str(e))
        
        if action_type == "spawn_agent":
            return await self._action_spawn_agent(config, event)
        elif action_type == "update_state":
            return await self._action_update_state(config, event)
        elif action_type == "call_api":
            return await self._action_call_api(config, event)
        elif action_type == "send_message":
            return await self._action_send_message(config, event)
        elif action_type == "update_workflow":
            return await self._action_update_workflow(config, event)
        elif action_type == "trigger_signal":
            return await self._action_trigger_signal(config, event)
        elif action_type == "execute_task":
            return await self._action_execute_task(config, event)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def _evaluate_condition(self, expr: Any, context: Dict[str, Any]) -> bool:
        """Evaluate a minimal JSONLogic-like expression against context.
        Supported ops: var, ==, !=, >, <, >=, <=, and, or, !, length
        Examples:
          {"==": [{"var": "event.data.severity"}, "high"]}
          {">": [{"var": "state.check_bookings.alternatives.length"}, 0]}
        """
        try:
            if expr is None:
                return True
            if isinstance(expr, bool):
                return bool(expr)
            if isinstance(expr, (int, float)):
                return bool(expr)
            if isinstance(expr, dict):
                if not expr:
                    return True
                op, val = next(iter(expr.items()))
                def resolve(v):
                    if isinstance(v, dict) and 'var' in v:
                        return self._resolve_var(v['var'], context)
                    if isinstance(v, dict) and 'length' in v:
                        target = resolve(v['length'])
                        if isinstance(target, (list, str, dict)):
                            return len(target)
                        return 0
                    if isinstance(v, list):
                        return [resolve(x) for x in v]
                    return v
                if op == 'var':
                    return bool(resolve({'var': val}))
                if op in ('==', '!=', '>', '<', '>=', '<='):
                    a, b = [resolve(x) for x in (val[0], val[1])]
                    if op == '==': return a == b
                    if op == '!=': return a != b
                    if op == '>': return a > b
                    if op == '<': return a < b
                    if op == '>=': return a >= b
                    if op == '<=': return a <= b
                if op == 'and':
                    return all(resolve(x) for x in val)
                if op == 'or':
                    return any(resolve(x) for x in val)
                if op == '!':
                    return not bool(resolve(val))
                if op == 'length':
                    target = resolve(val)
                    if isinstance(target, (list, str, dict)):
                        return len(target) > 0
                    return False
                # Unknown op => treat as truthy
                return True
            # Fallback truthiness
            return bool(expr)
        except Exception:
            return True

    def _resolve_var(self, path: str, context: Dict[str, Any]) -> Any:
        cur = context
        for part in str(path).split('.'):
            if part == 'length':
                if isinstance(cur, (list, str, dict)):
                    cur = len(cur)
                else:
                    return 0
                continue
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur
    
    async def _action_spawn_agent(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Spawn a new agent."""
        template_name = config.get('template')
        parameters = config.get('parameters', {})
        
        # Substitute event data in parameters
        parameters = self._substitute_event_data(parameters, event)
        
        # Keep workflow_id if present on event (legacy), but do not create workflows.
        workflow_id = event.workflow_id
        
        # Create agent configuration (map callback config to AgentConfig contract)
        agent_name = config.get('name', f"{template_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}")
        agent_type_str = config.get('type', 'worker')
        # Construct a minimal AgentConfig with sensible defaults
        agent_config = AgentConfig(
            name=agent_name,
            type=agent_type_str,
            version=config.get('version', '1.0.0'),
            capabilities=[
                # If explicit capabilities provided, translate them to CapabilityConfig entries
            ] if not config.get('capabilities') else [
                CapabilityConfig(tool=c.get('tool'), config=c.get('config', {}))
                for c in config.get('capabilities', [])
            ],
            prompt_template=config.get('system_prompt', ''),
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
            state_schema=StateSchema(required=[], output=[]),
            resources=ResourceConstraints(
                model=str(config.get('model', 'gpt-4')),
                max_tokens=int(config.get('max_tokens', 2048)),
                timeout=int(config.get('timeout', 30))
            ),
            success_metrics=[]
        )
        
        # Create agent instance
        if template_name:
            # Use template-based agent
            agent = ConfigurableAgent(config=agent_config)
        else:
            # Use factory to create typed agent
            agent = AgentFactory.create(
                agent_type=config.get('agent_type', 'worker'),
                agent_id=agent_config.name,
                config=parameters
            )
        
        # Execute agent if configured
        if config.get('execute_immediately', True):
            # Would execute agent here
            pass
        
        return {
            'action': 'spawn_agent',
            'agent_id': agent_config.name,
            'workflow_id': workflow_id,
            'status': 'created'
        }
    
    async def _action_update_state(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Update agent state (workflow state updates are deprecated)."""
        target_type = config.get('target', 'agent')  # agent only
        target_id = config.get('target_id') or event.workflow_id
        state_updates = config.get('updates', {})
        
        # Substitute event data
        state_updates = self._substitute_event_data(state_updates, event)
        
        if target_type == 'agent' and self._state_store:
            # Update agent state
            agent_id = config.get('agent_id') or event.agent_id
            if agent_id:
                await self._state_store.save_state(
                    agent_id=agent_id,
                    state_data=state_updates
                )
                return {
                    'action': 'update_state',
                    'target': 'agent',
                    'target_id': agent_id,
                    'updates': state_updates,
                    'success': True
                }
        
        if target_type == 'workflow':
            return {
                'action': 'update_state',
                'target': 'workflow',
                'target_id': target_id,
                'error': 'Workflow state updates are deprecated'
            }

        return {
            'action': 'update_state',
            'error': 'No valid target for state update'
        }
    
    async def _action_call_api(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Call an external API."""
        import aiohttp
        try:
            # Substitute event data in URL, headers, and body
            endpoint = self._substitute_event_data(config.get('endpoint', ''), event)
            if not endpoint:
                return {
                    'action': 'call_api',
                    'error': 'Missing endpoint'
                }

            method = (config.get('method') or 'POST').upper()
            headers = self._substitute_event_data(config.get('headers', {}), event) or {}
            body = self._substitute_event_data(config.get('body', {}), event)
            timeout = aiohttp.ClientTimeout(total=float(config.get('timeout', 10)))

            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    json=body if method in ['POST', 'PUT', 'PATCH'] else None,
                    timeout=timeout,
                ) as resp:
                    content_type = resp.headers.get('content-type', '')
                    try:
                        resp_body = await resp.json() if 'application/json' in content_type else await resp.text()
                    except Exception:
                        resp_body = await resp.text()

                    return {
                        'action': 'call_api',
                        'endpoint': endpoint,
                        'method': method,
                        'status_code': resp.status,
                        'response': resp_body,
                    }
        except Exception as e:
            logger.error("call_api failed", error=str(e), endpoint=config.get('endpoint'))
            return {
                'action': 'call_api',
                'endpoint': config.get('endpoint'),
                'error': str(e)
            }
    
    async def _action_send_message(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Send a message to another agent or system."""
        # This would integrate with message broker
        # For now, return placeholder
        return {
            'action': 'send_message',
            'target': config.get('target'),
            'message_type': config.get('message_type'),
            'status': 'not_implemented'
        }
    
    async def _action_update_workflow(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Workflow actions are deprecated."""
        logger.warning("Deprecated workflow action requested", action="update_workflow", event_id=event.id)
        return {
            'action': 'update_workflow',
            'error': 'Workflow actions are deprecated. Use tasks/triggers instead.'
        }

    async def _action_trigger_signal(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """Workflow actions are deprecated."""
        logger.warning("Deprecated workflow action requested", action="trigger_signal", event_id=event.id)
        return {
            'action': 'trigger_signal',
            'error': 'Workflow actions are deprecated. Use tasks/triggers instead.'
        }

    async def _action_execute_task(self, config: Dict[str, Any], event: Event) -> Dict[str, Any]:
        """
        Execute a task triggered by an event.

        This action clones a template task, injects event data into the clone's
        metadata, and executes it. This enables event-driven task execution
        where tasks are configured with triggers that respond to external events.

        Config:
            - task_id: Task ID to execute (required) - can use ${event.*} substitution
            - clone: Whether to clone the task (default: True for templates)

        The task receives event data in metadata:
            - trigger_event.id: Event ID
            - trigger_event.type: Event type (e.g., "external.integration.webhook")
            - trigger_event.source: Event source
            - trigger_event.data.*: Event data payload
            - trigger_event.metadata.*: Event metadata (e.g., application_id, interaction_token)
            - trigger_event.timestamp: Event timestamp

        Step inputs can reference trigger data via ${trigger_event.*} patterns.

        Returns:
            Dict with action result including executed_task_id and status
        """
        from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases

        task_id = self._substitute_event_data(config.get('task_id', ''), event)
        if not task_id:
            logger.error("execute_task action missing task_id", config=config)
            return {'action': 'execute_task', 'error': 'Missing task_id', 'success': False}

        should_clone = config.get('clone', True)

        try:
            task_use_cases = await provider_get_task_use_cases()

            # Build trigger event data to inject
            trigger_event_data = {
                'id': event.id,
                'type': event.event_type,
                'source': event.source,
                'data': event.data or {},
                'metadata': event.metadata or {},
                'timestamp': event.timestamp.isoformat() if event.timestamp else datetime.utcnow().isoformat(),
            }

            task_user_id = None
            if should_clone:
                # Clone the template task with event data injected
                cloned_task = await task_use_cases.clone_task_for_trigger(
                    template_task_id=task_id,
                    trigger_event=trigger_event_data,
                )
                executed_task_id = cloned_task.id
                task_user_id = cloned_task.user_id

                logger.info(
                    "Cloned task for trigger execution",
                    template_task_id=task_id,
                    cloned_task_id=cloned_task.id,
                    event_id=event.id,
                )
            else:
                # Execute directly without cloning (rare case)
                executed_task_id = task_id
                # Inject trigger event into existing task metadata
                task = await task_use_cases.get_task(task_id)
                if not task:
                    return {
                        'action': 'execute_task',
                        'error': f'Task not found: {task_id}',
                        'success': False
                    }

                task.metadata['trigger_event'] = trigger_event_data
                await task_use_cases.update_task_metadata(
                    task_id=task_id,
                    metadata=task.metadata,
                )
                task_user_id = task.user_id

            # Start task execution asynchronously
            result = await task_use_cases.start_task(
                task_id=executed_task_id,
                user_id=task_user_id,
            )

            status = result.get('status', 'unknown')

            logger.info(
                "Task triggered by event",
                template_task_id=task_id,
                executed_task_id=executed_task_id,
                event_id=event.id,
                status=status,
            )

            return {
                'action': 'execute_task',
                'template_task_id': task_id,
                'executed_task_id': executed_task_id,
                'event_id': event.id,
                'status': status,
                'success': True
            }

        except Exception as e:
            logger.error(
                "Failed to execute task",
                task_id=task_id,
                event_id=event.id,
                error=str(e),
                exc_info=True,
            )
            return {
                'action': 'execute_task',
                'task_id': task_id,
                'error': str(e),
                'success': False
            }
    def _evaluate_condition(self, condition: str, event: Event) -> bool:
        """Evaluate a condition against event data."""
        # Simple evaluation - in production would use safe expression evaluator
        try:
            # Create evaluation context
            context = {
                'event': event.data,
                'metadata': event.metadata,
                'event_type': event.event_type,
                'source': event.source
            }
            
            # Very basic condition evaluation
            # In production, use a proper expression evaluator like simpleeval
            if '>' in condition or '<' in condition or '==' in condition:
                # Extract simple comparisons
                # This is a placeholder - real implementation would be more robust
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}", condition=condition)
            return False
    
    def _substitute_event_data(self, data: Any, event: Event) -> Any:
        """Substitute event data in configuration."""
        if isinstance(data, str):
            # Replace ${event.field} with actual values
            if '${' in data:
                # Simple substitution - in production use proper template engine
                replacements = {
                    '${event.id}': event.id,
                    '${event.type}': event.event_type,
                    '${event.source}': event.source,
                    '${event.workflow_id}': event.workflow_id or '',
                    '${event.agent_id}': event.agent_id or ''
                }
                
                for key, value in replacements.items():
                    data = data.replace(key, str(value))
                
                # Handle nested event data
                if '${event.' in data:
                    import re
                    # Handle ${event.data.*}
                    pattern = r'\$\{event\.data\.([^}]+)\}'
                    matches = re.findall(pattern, data)
                    for match in matches:
                        value = self._get_nested_value(event.data or {}, match)
                        data = data.replace(f'${{event.data.{match}}}', str(value))

                    # Handle ${event.metadata.*}
                    pattern = r'\$\{event\.metadata\.([^}]+)\}'
                    matches = re.findall(pattern, data)
                    for match in matches:
                        value = self._get_nested_value(event.metadata or {}, match)
                        data = data.replace(f'${{event.metadata.{match}}}', str(value))
            
            return data
            
        elif isinstance(data, dict):
            return {k: self._substitute_event_data(v, event) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._substitute_event_data(v, event) for v in data]
        else:
            return data
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return ''
        return value
    
    async def _check_rate_limit(self, callback_id: str, limit: int, window: str) -> bool:
        """Check if callback is within rate limit."""
        # Parse window (e.g., "1h", "10m", "30s")
        window_seconds = self._parse_time_window(window)
        
        # Use Redis for rate limiting
        rate_key = f"{self._key_prefix}:rate:{callback_id}"
        current_time = int(datetime.utcnow().timestamp())
        window_start = current_time - window_seconds
        
        # Count recent executions
        count = await self._redis_client.zcount(rate_key, window_start, current_time)
        
        return count < limit
    
    def _parse_time_window(self, window: str) -> int:
        """Parse time window string to seconds."""
        if window.endswith('h'):
            return int(window[:-1]) * 3600
        elif window.endswith('m'):
            return int(window[:-1]) * 60
        elif window.endswith('s'):
            return int(window[:-1])
        else:
            return int(window)  # Assume seconds
    
    async def _record_execution(self, execution: CallbackExecution):
        """Record callback execution for rate limiting."""
        # Store in Redis sorted set
        rate_key = f"{self._key_prefix}:rate:{execution.callback_id}"
        timestamp = int(execution.timestamp.timestamp())
        
        await self._redis_client.zadd(
            rate_key,
            {f"{execution.timestamp.isoformat()}": timestamp}
        )
        
        # Expire old entries
        await self._redis_client.expire(rate_key, 86400)  # 24 hours
    
    async def _update_metrics(self, callback_id: str, execution: CallbackExecution):
        """Update callback execution metrics."""
        metrics_key = f"{self._key_prefix}:metrics:{callback_id}"
        
        # Get current metrics
        metrics = await self._redis_client.hgetall(metrics_key)
        
        total = int(metrics.get('total_executions', 0)) + 1
        successful = int(metrics.get('successful_executions', 0))
        failed = int(metrics.get('failed_executions', 0))
        
        if execution.success:
            successful += 1
        else:
            failed += 1
        
        # Update metrics
        await self._redis_client.hset(
            metrics_key,
            mapping={
                'total_executions': str(total),
                'successful_executions': str(successful),
                'failed_executions': str(failed),
                'last_execution': execution.timestamp.isoformat()
            }
        )
        
        # Set expiry
        await self._redis_client.expire(metrics_key, 2592000)  # 30 days
    
    async def _ensure_initialized(self):
        """Ensure engine is initialized."""
        if not self._initialized:
            await self.initialize()
    
    async def cleanup(self):
        """Cleanup resources."""
        if self._redis_client:
            await self._redis_client.aclose()
        self._initialized = False
        logger.info("Callback Engine cleaned up")
