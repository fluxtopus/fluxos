# REVIEW:
# - LLM client lifecycle managed via manual __aenter__/__aexit__; easy to leak if initialize isn't called.
# - Model/temperature defaults are hard-coded in metadata; config spread across multiple places.
import asyncio
from typing import Any, Dict, List, Optional
import time
from src.agents.conversation_aware_agent import ConversationAwareAgent
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.llm.openrouter_client import OpenRouterClient
from src.core.config import settings
import structlog
import json

logger = structlog.get_logger()


class LLMAgent(ConversationAwareAgent):
    """Agent powered by LLM for intelligent task processing with automatic conversation tracking"""

    def __init__(
        self,
        config: 'AgentConfig',
        llm_client: Optional[LLMInterface] = None,
        enable_conversation_tracking: bool = True
    ):
        # Extract LLM-specific configuration from metadata
        from src.agents.stateful_agent import StatefulAgentConfig
        from src.infrastructure.state.redis_state_store import RedisStateStore
        from src.agents.base import AgentConfig

        metadata = config.metadata if hasattr(config, 'metadata') else {}

        # Create StatefulAgentConfig
        stateful_config = StatefulAgentConfig(
            name=config.name,
            agent_type=config.agent_type if hasattr(config, 'agent_type') else "llm_agent",
            state_store=RedisStateStore(
                redis_url=settings.REDIS_URL.replace('/0', '/7'),  # Use DB 7 for LLM agents
                db=7
            )
        )
        super().__init__(stateful_config, enable_conversation_tracking)

        # Store configuration
        self.name = config.name
        self.llm_client = llm_client
        self.model = metadata.get('model', 'x-ai/grok-3-mini')
        self.temperature = metadata.get('temperature', 0.7)
        self.system_prompt = metadata.get('system_prompt') or self._default_system_prompt()
        self._client_context = None
        self._wrapped_client = None
    
    def _default_system_prompt(self) -> str:
        return """You are an intelligent agent in the Tentackl multi-agent system.
Your role is to process tasks efficiently and provide structured responses.
Always respond with valid JSON containing:
- status: "success" or "error"
- result: the output of your task
- metadata: any additional information
"""
    
    async def initialize(
        self,
        context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        execution_node_id: Optional[str] = None
    ) -> None:
        """Initialize the LLM agent with conversation tracking"""
        try:
            await super().initialize(context_id, tree_id, execution_node_id)

            # Create LLM client if not provided
            if not self.llm_client:
                logger.info(f"Creating OpenRouterClient for agent {self.name}")
                self.llm_client = OpenRouterClient()
                self._client_context = self.llm_client
                await self._client_context.__aenter__()
                logger.info(f"OpenRouterClient initialized for agent {self.name}")

            # Wrap LLM client with conversation interceptor if tracking is enabled
            if self.enable_conversation_tracking and self.conversation_interceptor:
                self._wrapped_client = ConversationAwareLLMWrapper(
                    self.llm_client,
                    self.conversation_interceptor,
                    self.agent_id,
                    self.model,
                    agent_ref=self  # Pass reference to self for context access
                )
                logger.info(f"LLM client wrapped with conversation tracking for agent {self.name}")
            else:
                self._wrapped_client = self.llm_client
                logger.info(f"Using direct LLM client (no conversation tracking) for agent {self.name}")

            # Verify we have a client
            if not self._wrapped_client:
                raise ValueError(f"Failed to create LLM client for agent {self.name}")

            # Verify LLM connectivity
            try:
                health = await self.llm_client.health_check()
                self._llm_healthy = bool(health)
                if health:
                    logger.info(f"LLM agent {self.name} initialized successfully with model {self.model}")
                else:
                    logger.warning(f"LLM health check failed for agent {self.name}, but continuing")
            except Exception as e:
                logger.warning(f"LLM health check error for agent {self.name}: {str(e)}, but continuing")
                # Don't fail initialization on health check failure
                self._llm_healthy = False

        except Exception as e:
            logger.error(f"Failed to initialize LLM agent {self.name}", error=str(e), agent_id=self.agent_id)
            raise
    
    async def cleanup(self) -> None:
        """Cleanup LLM resources"""
        if self._client_context:
            await self._client_context.__aexit__(None, None, None)
        await super().cleanup()
    
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """Execute LLM agent logic with state management"""
        return await self.process_task(task)
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process task using LLM"""
        try:
            # Ensure we have a client to use
            client_to_use = self._wrapped_client if self._wrapped_client else self.llm_client
            if not client_to_use:
                logger.error(
                    f"No LLM client available for agent {self.name}",
                    wrapped_client_exists=bool(self._wrapped_client),
                    llm_client_exists=bool(self.llm_client),
                    agent_id=self.agent_id
                )
                raise ValueError(f"No LLM client available for agent {self.name} (wrapped:{bool(self._wrapped_client)}, base:{bool(self.llm_client)})")
            # Build conversation messages
            messages = [
                LLMMessage(role="system", content=self.system_prompt)
            ]
            
            # Add task context
            # Support multiple input formats:
            # 1. "prompt" key: direct LLM prompt (preferred for workflow configs)
            # 2. "task" key with other inputs: combine task description with input data
            # 3. "description"+"data" keys: structured task mode
            # 4. All other keys: treat as structured data inputs

            if "prompt" in task:
                # Direct prompt mode - use the prompt as-is
                user_message = task["prompt"]
            elif "task" in task:
                # Task mode - combine task description with other inputs
                task_instruction = task["task"]

                # Collect all other inputs (exclude known metadata keys)
                exclude_keys = {"task", "prompt", "description", "max_tokens", "id", "node_id", "workflow_id"}
                other_inputs = {k: v for k, v in task.items() if k not in exclude_keys}

                if other_inputs:
                    # Format inputs in a readable way
                    inputs_text = "\n\n".join([
                        f"{key.replace('_', ' ').title()}:\n{value}"
                        for key, value in other_inputs.items()
                    ])
                    user_message = f"{task_instruction}\n\n{inputs_text}"
                else:
                    user_message = task_instruction
            else:
                # Structured task mode
                task_description = task.get("description", "Process this task")
                task_data = task.get("data", {})

                user_message = f"""Task: {task_description}
Data: {json.dumps(task_data, indent=2)}

Please process this task and return a JSON response."""

            messages.append(LLMMessage(role="user", content=user_message))
            
            # Get LLM response using wrapped client (which handles interception)
            response = await client_to_use.create_completion(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=task.get("max_tokens", 4000)
            )
            
            # Check if we got a valid response
            if not response:
                raise ValueError("No response received from LLM client")
            
            # Parse response
            try:
                parsed = json.loads(response.content)
                if isinstance(parsed, dict):
                    result = dict(parsed)
                    result.setdefault("status", "success")
                    if not isinstance(result.get("metadata"), dict):
                        result["metadata"] = {}
                else:
                    result = {
                        "status": "success",
                        "result": parsed,
                        "metadata": {},
                    }
            except json.JSONDecodeError:
                # If response is not JSON, wrap it
                result = {
                    "status": "success",
                    "result": response.content,
                    "metadata": {"raw_response": True}
                }
            
            # Add model info to metadata
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"].setdefault("model", getattr(response, "model", self.model))
            if hasattr(response, "usage") and response.usage:
                result["metadata"].setdefault("usage", response.usage)
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"LLM processing failed", error=str(e), task_id=task.get("id"), traceback=traceback.format_exc())
            
            # Log error to conversation if interceptor is available
            if self.conversation_interceptor:
                await self.conversation_interceptor.intercept_error(
                    self.agent_id,
                    e,
                    {"task": task}
                )
            # Decide whether to propagate or return structured error
            if getattr(self, "_raise_on_llm_error", False):
                raise
            return {
                "status": "error",
                "error": str(e),
                "metadata": {"agent": self.name}
            }


class LLMWorkerAgent(LLMAgent):
    """Worker agent powered by LLM for general task processing"""

    def __init__(
        self,
        config: 'AgentConfig',
        llm_client: Optional[LLMInterface] = None,
        enable_conversation_tracking: bool = True
    ):
        # Set default system prompt in metadata if not provided
        from src.agents.base import AgentConfig
        if not config.metadata.get('system_prompt'):
            config.metadata['system_prompt'] = """You are a worker agent in the Tentackl system.
Process tasks efficiently and provide clear, actionable results.
Focus on:
1. Understanding the task requirements
2. Processing data accurately
3. Providing structured outputs
4. Handling errors gracefully
"""
        # Set default model and temperature if not provided
        if 'model' not in config.metadata:
            config.metadata['model'] = 'x-ai/grok-3-mini'
        if 'temperature' not in config.metadata:
            config.metadata['temperature'] = 0.7

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking
        )


class LLMAnalyzerAgent(LLMAgent):
    """Analyzer agent powered by LLM for data analysis tasks"""

    def __init__(
        self,
        config: 'AgentConfig',
        llm_client: Optional[LLMInterface] = None,
        enable_conversation_tracking: bool = True
    ):
        # Set default system prompt in metadata if not provided
        from src.agents.base import AgentConfig
        if not config.metadata.get('system_prompt'):
            config.metadata['system_prompt'] = """You are an analyzer agent specialized in data analysis.
Your responsibilities:
1. Analyze data patterns and trends
2. Identify anomalies or issues
3. Generate insights and recommendations
4. Provide statistical summaries when relevant
5. Create visualizable data structures

Always structure your analysis with:
- summary: Brief overview of findings
- details: In-depth analysis
- insights: Key takeaways
- recommendations: Actionable next steps
"""
        # Set default model and temperature if not provided
        if 'model' not in config.metadata:
            config.metadata['model'] = 'openai/gpt-4o'  # Use more powerful model for analysis
        if 'temperature' not in config.metadata:
            config.metadata['temperature'] = 0.3  # Lower temperature for more consistent analysis

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking
        )


class LLMValidatorAgent(LLMAgent):
    """Validator agent powered by LLM for validation tasks"""

    def __init__(
        self,
        config: 'AgentConfig',
        llm_client: Optional[LLMInterface] = None,
        enable_conversation_tracking: bool = True
    ):
        # Set default system prompt in metadata if not provided
        from src.agents.base import AgentConfig
        if not config.metadata.get('system_prompt'):
            config.metadata['system_prompt'] = """You are a validator agent responsible for data validation.
Your tasks include:
1. Validating data against schemas and rules
2. Checking data quality and completeness
3. Identifying validation errors
4. Suggesting corrections

Return validation results as:
{
    "status": "valid" or "invalid",
    "errors": [...],
    "warnings": [...],
    "suggestions": [...],
    "metadata": {...}
}
"""
        # Set default model and temperature if not provided
        if 'model' not in config.metadata:
            config.metadata['model'] = 'x-ai/grok-3-mini'
        if 'temperature' not in config.metadata:
            config.metadata['temperature'] = 0.1  # Very low temperature for consistent validation

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking
        )


class LLMOrchestratorAgent(LLMAgent):
    """Orchestrator agent powered by LLM for workflow coordination"""

    def __init__(
        self,
        config: 'AgentConfig',
        llm_client: Optional[LLMInterface] = None,
        enable_conversation_tracking: bool = True
    ):
        # Set default system prompt in metadata if not provided
        from src.agents.base import AgentConfig
        if not config.metadata.get('system_prompt'):
            config.metadata['system_prompt'] = """You are an orchestrator agent managing complex workflows.
Your responsibilities:
1. Break down complex tasks into sub-tasks
2. Determine optimal agent assignments
3. Define execution order and dependencies
4. Monitor progress and adapt plans
5. Aggregate results from multiple agents

When creating execution plans, structure them as:
{
    "plan": {
        "steps": [...],
        "dependencies": {...},
        "agent_assignments": {...},
        "expected_outcomes": {...}
    },
    "metadata": {...}
}
"""
        # Set default model and temperature if not provided
        if 'model' not in config.metadata:
            config.metadata['model'] = 'x-ai/grok-4.1-fast'
        if 'temperature' not in config.metadata:
            config.metadata['temperature'] = 0.5

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking
        )
    
    async def create_execution_plan(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Create an execution plan for a complex task"""
        planning_task = {
            "description": "Create execution plan",
            "data": {
                "original_task": task,
                "available_agents": ["worker", "analyzer", "validator", "transformer"],
                "constraints": task.get("constraints", {})
            }
        }
        
        return await self.process_task(planning_task)


class ConversationAwareLLMWrapper:
    """Wrapper for LLM clients that intercepts calls for conversation tracking."""
    
    def __init__(self, client: LLMInterface, interceptor, agent_id: str, default_model: str, agent_ref=None):
        self.client = client
        self.interceptor = interceptor
        self.agent_id = agent_id
        self.default_model = default_model
        self.agent_ref = agent_ref  # Reference to parent agent for context
    
    async def create_completion(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """Create completion with conversation tracking."""
        start_time = time.time()
        
        # Extract the prompt (last user message)
        prompt = messages[-1].content if messages else ""
        model = kwargs.get("model", self.default_model)
        
        
        # Debug logging
        from src.database.conversation_interceptor import current_conversation_id, current_agent_id
        
        # Check if context needs to be set from parent agent
        if self.agent_ref and hasattr(self.agent_ref, 'current_conversation_id'):
            conv_id = self.agent_ref.current_conversation_id
            if conv_id and not current_conversation_id.get():
                current_conversation_id.set(conv_id)
                current_agent_id.set(self.agent_id)
                logger.debug(f"Set context from agent: conversation_id={conv_id}, agent_id={self.agent_id}")
        
        logger.debug(f"Wrapper: current_conversation_id={current_conversation_id.get()}, current_agent_id={current_agent_id.get()}")
        
        # Intercept outgoing call
        # Remove model from kwargs if it exists to avoid duplicate
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop('model', None)
        
        prompt_interception = await self.interceptor.intercept_llm_call(
            agent_id=self.agent_id,
            prompt=prompt,
            model=model,
            **kwargs_copy
        )
        
        try:
            # Make actual LLM call
            response = await self.client.create_completion(messages, **kwargs)
            
            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Intercept response - pass the actual response object
            await self.interceptor.intercept_llm_response(
                agent_id=self.agent_id,
                response=response,
                latency_ms=latency_ms,
                parent_message_id=prompt_interception.message_id
            )
            
            return response
            
        except Exception as e:
            # Intercept error
            await self.interceptor.intercept_error(
                self.agent_id,
                e,
                {"messages": [{"role": m.role, "content": m.content} for m in messages], "kwargs": kwargs}
            )
            # Propagate to caller (process_task may convert to error result if not in execute path)
            raise
    
    async def create_completion_stream(self, messages: List[LLMMessage], **kwargs):
        """Pass through streaming (not tracked yet)."""
        async for chunk in self.client.create_completion_stream(messages, **kwargs):
            yield chunk
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Pass through model listing."""
        return await self.client.list_models()
    
    async def health_check(self) -> bool:
        """Pass through health check."""
        return await self.client.health_check()
