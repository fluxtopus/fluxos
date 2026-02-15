"""
# REVIEW:
# - Async load_config kicked off via create_task in __init__; errors can be unobserved and state can be used before ready.
# - ConfigurableAgent mixes validation, capability binding, metrics, and execution; large surface area.

Configurable Agent Implementation

This module implements the ConfigurableAgent that can interpret and execute
configurations at runtime, forming the foundation of the config-based
agent generation architecture.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
import uuid

from ..interfaces.configurable_agent import (
    ConfigurableAgentInterface,
    AgentConfig,
    ExecutionStrategy,
    CapabilityConfig,
    StateSchema,
    SuccessMetric
)
from ..interfaces.agent import AgentState, AgentCapability, AgentResult
from ..interfaces.state_store import StateStoreInterface, StateType, StateSnapshot
from ..interfaces.context_manager import ContextManagerInterface
from ..interfaces.budget_controller import (
    BudgetControllerInterface,
    ResourceType
)
from ..core.exceptions import (
    AgentExecutionError,
    ValidationError,
    CapabilityNotFoundError
)
from ..core.safe_eval import safe_eval_condition
import structlog

logger = structlog.get_logger(__name__)


class ConfigurableAgent(ConfigurableAgentInterface):
    """Agent that interprets configurations at runtime"""
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        budget_controller: Optional[BudgetControllerInterface] = None,
        state_store: Optional[StateStoreInterface] = None,
        context_manager: Optional[ContextManagerInterface] = None,
        capability_binder = None,
        prompt_executor = None,
        tool_executor = None
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.config = config
        self.budget_controller = budget_controller
        self.state_store = state_store
        self.context_manager = context_manager
        self.capability_binder = capability_binder
        self.prompt_executor = prompt_executor
        self.tool_executor = tool_executor
        
        # Runtime state
        self._capabilities: Dict[str, Any] = {}
        self._state: Dict[str, Any] = {}
        self._metrics: Dict[str, float] = {}
        self._execution_count = 0
        self._created_at = datetime.utcnow()
        
        # Load config if provided
        if config:
            asyncio.create_task(self.load_config(config))
    
    async def load_config(self, config: AgentConfig) -> None:
        """Load configuration into the agent"""
        try:
            self.config = config
            
            # Validate config
            validation_result = await self._validate_config(config)
            if not validation_result["valid"]:
                raise ValidationError(
                    f"Invalid configuration: {validation_result['errors']}"
                )
            
            # Initialize state schema
            await self._initialize_state_schema(config.state_schema)
            
            # Bind capabilities
            if self.capability_binder:
                for capability in config.capabilities:
                    if await self.capability_binder.validate_capability(capability):
                        await self.capability_binder.bind_capability(self, capability)
                        self._capabilities[capability.tool] = capability
                    else:
                        logger.warning(
                            "Capability not available",
                            capability=capability.tool,
                            agent_id=self.agent_id
                        )
            
            # Initialize metrics
            for metric in config.success_metrics:
                self._metrics[metric.metric] = 0.0
            
            logger.info(
                "Configuration loaded",
                agent_id=self.agent_id,
                name=config.name,
                type=config.type,
                capabilities=len(self._capabilities)
            )
            
        except Exception as e:
            logger.error(
                "Failed to load configuration",
                error=str(e),
                agent_id=self.agent_id
            )
            raise
    
    async def reload_config(self, config: AgentConfig) -> None:
        """Reload configuration (hot reload)"""
        try:
            # Save current state
            current_state = self._state.copy()
            
            # Clear runtime data
            self._capabilities.clear()
            self._metrics.clear()
            
            # Load new config
            await self.load_config(config)
            
            # Restore compatible state
            restored_state = {}
            for key in config.state_schema.required:
                if key in current_state:
                    restored_state[key] = current_state[key]
            
            self._state = restored_state
            
            logger.info(
                "Configuration reloaded",
                agent_id=self.agent_id,
                preserved_keys=list(restored_state.keys())
            )
            
        except Exception as e:
            logger.error(
                "Failed to reload configuration",
                error=str(e),
                agent_id=self.agent_id
            )
            raise
    
    async def get_config(self) -> AgentConfig:
        """Get current configuration"""
        if not self.config:
            raise ValueError("No configuration loaded")
        return self.config
    
    async def validate_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate state against schema"""
        if not self.config:
            raise ValueError("No configuration loaded")
        
        errors = []
        warnings = []
        
        # Check required fields
        for field in self.config.state_schema.required:
            if field not in state:
                errors.append(f"Required field missing: {field}")
        
        # Check output fields are defined
        for field in self.config.state_schema.output:
            if field not in state:
                warnings.append(f"Output field not set: {field}")
        
        # Run custom validation rules
        if self.config.state_schema.validation_rules:
            for field, rules in self.config.state_schema.validation_rules.items():
                if field in state:
                    value = state[field]
                    # Example validation rules
                    if "type" in rules:
                        expected_type = rules["type"]
                        if expected_type == "str" and not isinstance(value, str):
                            errors.append(
                                f"Field {field} has wrong type: expected {expected_type}"
                            )
                        elif expected_type == "int" and not isinstance(value, int):
                            errors.append(
                                f"Field {field} has wrong type: expected {expected_type}"
                            )
                        elif expected_type == "float" and not isinstance(value, (int, float)):
                            errors.append(
                                f"Field {field} has wrong type: expected {expected_type}"
                            )
                    
                    # Type check before comparison
                    if "min" in rules and isinstance(value, (int, float)) and value < rules["min"]:
                        errors.append(
                            f"Field {field} below minimum: {value} < {rules['min']}"
                        )
                    if "max" in rules and isinstance(value, (int, float)) and value > rules["max"]:
                        errors.append(
                            f"Field {field} above maximum: {value} > {rules['max']}"
                        )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def check_success_metrics(
        self,
        execution_result: Any
    ) -> Dict[str, bool]:
        """Check if success metrics are met"""
        if not self.config:
            raise ValueError("No configuration loaded")
        
        results = {}
        
        for metric in self.config.success_metrics:
            # Extract metric value from result
            metric_value = self._extract_metric_value(
                execution_result,
                metric.metric
            )
            
            # Update internal metrics
            self._metrics[metric.metric] = metric_value
            
            # Check against threshold
            if metric.operator == "gte":
                results[metric.metric] = metric_value >= metric.threshold
            elif metric.operator == "lte":
                results[metric.metric] = metric_value <= metric.threshold
            elif metric.operator == "eq":
                results[metric.metric] = metric_value == metric.threshold
            elif metric.operator == "neq":
                results[metric.metric] = metric_value != metric.threshold
            else:
                results[metric.metric] = False
        
        return results
    
    async def execute_with_strategy(
        self,
        task: Any,
        context: Dict[str, Any]
    ) -> Any:
        """Execute task with configured strategy"""
        if not self.config:
            raise ValueError("No configuration loaded")
        
        strategy = self.config.execution_strategy
        
        if strategy == ExecutionStrategy.SEQUENTIAL:
            return await self._execute_sequential(task, context)
        elif strategy == ExecutionStrategy.PARALLEL:
            return await self._execute_parallel(task, context)
        elif strategy == ExecutionStrategy.CONDITIONAL:
            return await self._execute_conditional(task, context)
        elif strategy == ExecutionStrategy.ITERATIVE:
            return await self._execute_iterative(task, context)
        else:
            raise ValueError(f"Unknown execution strategy: {strategy}")
    
    # AgentInterface implementation
    
    async def initialize(self) -> None:
        """Initialize the agent"""
        if not self.config:
            raise ValueError("No configuration loaded")
        
        # Initialize from state store if available
        if self.state_store:
            latest_state = await self.state_store.get_latest_state(
                self.agent_id,
                StateType.AGENT_STATE
            )
            if latest_state:
                self._state = latest_state.data
                logger.info(
                    "Restored from checkpoint",
                    agent_id=self.agent_id,
                    checkpoint_id=latest_state.id
                )
    
    async def execute(self, task: Any) -> AgentResult:
        """Execute a task"""
        start_time = datetime.utcnow()
        self._execution_count += 1
        
        try:
            if not self.config:
                raise ValueError("No configuration loaded")
            
            # Check budget if available
            if self.budget_controller:
                # Check LLM calls budget
                can_execute = await self.budget_controller.check_budget(
                    self.agent_id,
                    ResourceType.LLM_CALLS,
                    1
                )
                if not can_execute:
                    raise AgentExecutionError("Budget exceeded for LLM calls")
                
                # Check token budget
                estimated_tokens = self.config.resources.max_tokens
                can_execute = await self.budget_controller.check_budget(
                    self.agent_id,
                    ResourceType.LLM_TOKENS,
                    estimated_tokens
                )
                if not can_execute:
                    raise AgentExecutionError("Budget exceeded for tokens")
            
            # Get context
            context = {}
            if self.context_manager:
                agent_context = await self.context_manager.get_context(self.agent_id)
                if agent_context:
                    context = agent_context.data
            
            # Merge task into context
            if isinstance(task, dict):
                context.update(task)
            else:
                context["task"] = task
            
            # Add state to context
            context["state"] = self._state
            context["agent_id"] = self.agent_id
            context["execution_count"] = self._execution_count
            
            # Execute with prompt executor (with tool calling support if tool_executor is available)
            if self.prompt_executor:
                # Check if response format is specified
                response_format = None
                if hasattr(self.config.resources, 'response_format'):
                    response_format = self.config.resources.response_format
                elif isinstance(self.config.resources, dict) and 'response_format' in self.config.resources:
                    response_format = self.config.resources['response_format']
                
                # Get tool definitions if tool_executor is available
                tools = None
                if self.tool_executor:
                    tools = self.tool_executor.registry.get_tool_definitions()
                    logger.info(
                        "Agent has tool executor, enabling tool calling",
                        agent_id=self.agent_id,
                        tool_count=len(tools) if tools else 0
                    )
                
                # Execute with tool calling loop if tools are available
                if self.tool_executor and tools:
                    response = await self._execute_with_tool_calling(
                        self.config.prompt_template,
                        context,
                        self.config.resources.model,
                        self.config.resources.max_tokens,
                        getattr(self.config.resources, 'temperature', 0.7),
                        response_format,
                        tools,
                        max_rounds=5
                    )
                else:
                    # Simple prompt execution without tool calling
                    response = await self.prompt_executor.execute_prompt(
                        self.config.prompt_template,
                        context,
                        self.config.resources.model,
                        self.config.resources.max_tokens,
                        temperature=getattr(self.config.resources, 'temperature', 0.7),
                        response_format=response_format,
                        tools=None
                    )
            else:
                # Fallback execution
                response = await self.execute_with_strategy(task, context)
            
            # Log raw response from prompt executor
            logger.debug(
                "Prompt executor response received",
                agent_id=self.agent_id,
                response_type=type(response).__name__,
                response_is_dict=isinstance(response, dict),
                response_length=len(str(response)) if response else 0,
                response_preview=str(response)[:200] if response else None
            )
            
            # Ensure response is a dict. If string, clean code fences and parse JSON when possible
            if not isinstance(response, dict):
                if isinstance(response, str):
                    cleaned = self._clean_json_like_string(response)
                    try:
                        parsed = json.loads(cleaned)
                        response = parsed if isinstance(parsed, dict) else {"result": cleaned}
                        logger.debug(
                            "Parsed JSON from string response",
                            agent_id=self.agent_id,
                            parsed_type=type(parsed).__name__,
                            parsed_is_dict=isinstance(parsed, dict),
                            parsed_keys=list(parsed.keys())[:10] if isinstance(parsed, dict) else None
                        )
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Failed to parse JSON from response",
                            agent_id=self.agent_id,
                            error=str(e),
                            cleaned_preview=cleaned[:200]
                        )
                        response = {"result": cleaned}
                else:
                    response = {"result": response}
                    logger.debug(
                        "Wrapped non-string response",
                        agent_id=self.agent_id,
                        original_type=type(response.get("result")).__name__
                    )
            
            # Unwrap "result" key if response has it but doesn't have expected outputs
            # This handles cases where LLM wraps the response in {"result": {...}}
            if isinstance(response, dict) and "result" in response and len(response) == 1:
                expected_outputs = self.config.state_schema.output
                if expected_outputs and not all(out in response for out in expected_outputs):
                    # Check if the nested result has the expected outputs
                    nested_result = response.get("result")
                    if isinstance(nested_result, dict):
                        if all(out in nested_result for out in expected_outputs):
                            # Unwrap: use nested_result as the response
                            logger.debug(
                                "Unwrapping 'result' key to access expected outputs",
                                agent_id=self.agent_id,
                                nested_keys=list(nested_result.keys())[:10],
                                expected_outputs=expected_outputs
                            )
                            response = nested_result
                        elif any(out in nested_result for out in expected_outputs):
                            # Merge nested_result into response
                            logger.debug(
                                "Merging 'result' key with response",
                                agent_id=self.agent_id,
                                nested_keys=list(nested_result.keys())[:10],
                                expected_outputs=expected_outputs
                            )
                            response = {**response, **nested_result}
                            # Remove the "result" key if we've merged its contents
                            if "result" in response and all(out in response for out in expected_outputs):
                                response.pop("result", None)
            
            # Log parsed response structure before creating AgentResult
            logger.info(
                "Response parsed and ready for AgentResult",
                agent_id=self.agent_id,
                response_type=type(response).__name__,
                response_is_dict=isinstance(response, dict),
                response_keys=list(response.keys())[:10] if isinstance(response, dict) else None,
                response_size=len(response) if isinstance(response, dict) else None,
                response_empty=not response or (isinstance(response, dict) and len(response) == 0),
                expected_outputs=self.config.state_schema.output,
                has_expected_outputs=all(out in response for out in self.config.state_schema.output) if isinstance(response, dict) else False
            )
            
            # Update state with output
            for output_field in self.config.state_schema.output:
                if output_field in response:
                    self._state[output_field] = response[output_field]
            
            # Save checkpoint if enabled
            if (self.config.state_schema.checkpoint and 
                self.config.state_schema.checkpoint.get("enabled")):
                await self._save_checkpoint()
            
            # Consume budget
            if self.budget_controller:
                await self.budget_controller.consume_budget(
                    self.agent_id,
                    ResourceType.LLM_CALLS,
                    1
                )
                # Estimate actual tokens used
                actual_tokens = len(str(response)) // 4  # Rough estimate
                await self.budget_controller.consume_budget(
                    self.agent_id,
                    ResourceType.LLM_TOKENS,
                    actual_tokens
                )
            
            # Check success metrics
            metric_results = await self.check_success_metrics(response)
            all_success = all(metric_results.values())
            
            # Create result
            result = AgentResult(
                agent_id=self.agent_id,
                result=response,
                state=AgentState.COMPLETED if all_success else AgentState.FAILED,
                metadata={
                    "execution_time": (datetime.utcnow() - start_time).total_seconds(),
                    "metrics": metric_results,
                    "config_version": self.config.version
                }
            )
            
            # Log AgentResult creation details
            logger.info(
                "Task executed - AgentResult created",
                agent_id=self.agent_id,
                success=all_success,
                metrics=metric_results,
                execution_time=result.metadata["execution_time"],
                result_state=result.state.value if hasattr(result.state, 'value') else str(result.state),
                result_type=type(result.result).__name__,
                result_is_dict=isinstance(result.result, dict),
                result_keys=list(result.result.keys())[:10] if isinstance(result.result, dict) else None,
                result_size=len(result.result) if isinstance(result.result, dict) else None,
                result_empty=not result.result or (isinstance(result.result, dict) and len(result.result) == 0),
                expected_outputs=self.config.state_schema.output
            )
            
            # Warn if result is empty
            if not result.result or (isinstance(result.result, dict) and len(result.result) == 0):
                logger.error(
                    "ConfigurableAgent created empty AgentResult",
                    agent_id=self.agent_id,
                    agent_name=self.config.name,
                    response_value=str(response)[:500],
                    response_type=type(response).__name__,
                    expected_outputs=self.config.state_schema.output
                )
            
            return result
            
        except Exception as e:
            logger.error(
                "Task execution failed",
                error=str(e),
                agent_id=self.agent_id
            )
            
            return AgentResult(
                agent_id=self.agent_id,
                result=None,
                state=AgentState.FAILED,
                error=str(e),
                metadata={
                    "execution_time": (datetime.utcnow() - start_time).total_seconds(),
                    "config_version": self.config.version if self.config else None
                }
            )
    
    async def get_state(self) -> AgentState:
        """Get current agent state"""
        if self._execution_count == 0:
            return AgentState.IDLE
        elif self._execution_count > 0:
            return AgentState.COMPLETED
        else:
            return AgentState.FAILED
    
    async def get_capabilities(self) -> List[AgentCapability]:
        """Get agent capabilities"""
        # Convert string capabilities to AgentCapability enum
        capabilities = []
        for cap_name in self._capabilities.keys():
            try:
                capabilities.append(AgentCapability[cap_name.upper()])
            except KeyError:
                capabilities.append(AgentCapability.CUSTOM)
        return capabilities
    
    async def cleanup(self) -> None:
        """Cleanup agent resources"""
        # Save final state
        if self.state_store and self._state:
            snapshot = StateSnapshot(
                agent_id=self.agent_id,
                state_type=StateType.AGENT_STATE,
                data=self._state.copy(),
                metadata={"execution_count": self._execution_count}
            )
            await self.state_store.save_state(snapshot)
        
        # Clear runtime data
        self._capabilities.clear()
        self._state.clear()
        self._metrics.clear()
        
        logger.info(
            "Agent cleaned up",
            agent_id=self.agent_id,
            total_executions=self._execution_count
        )
    
    # Private helper methods
    
    async def _validate_config(self, config: AgentConfig) -> Dict[str, Any]:
        """Validate agent configuration"""
        errors = []
        warnings = []
        
        # Validate required fields
        if not config.name:
            errors.append("Agent name is required")
        if not config.type:
            errors.append("Agent type is required")
        if not config.prompt_template:
            errors.append("Prompt template is required")
        if not config.capabilities:
            warnings.append("No capabilities defined")
        
        # Validate resources
        if config.resources.max_tokens <= 0:
            errors.append("Max tokens must be positive")
        if config.resources.timeout <= 0:
            errors.append("Timeout must be positive")
        
        # Validate state schema
        if not config.state_schema.required and not config.state_schema.output:
            warnings.append("No state schema defined")
        
        # Validate metrics
        if not config.success_metrics:
            warnings.append("No success metrics defined")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    async def _initialize_state_schema(self, schema: StateSchema) -> None:
        """Initialize state based on schema"""
        # Initialize required fields with None
        for field in schema.required:
            if field not in self._state:
                self._state[field] = None
        
        # Initialize output fields
        for field in schema.output:
            if field not in self._state:
                self._state[field] = None
    
    async def _save_checkpoint(self) -> None:
        """Save state checkpoint"""
        if self.state_store:
            try:
                metadata = {
                    "execution_count": self._execution_count,
                    "metrics": self._metrics.copy(),
                    "config_version": self.config.version,
                }
                # Prefer legacy signature used in tests: (agent_id, StateType.CHECKPOINT, data, metadata)
                try:
                    checkpoint_type = getattr(StateType, 'CHECKPOINT', StateType.AGENT_STATE)
                    await self.state_store.save_state(
                        self.agent_id,
                        checkpoint_type,
                        self._state.copy(),
                        metadata,
                    )
                except TypeError:
                    # Fallback to snapshot-based interface
                    snapshot = StateSnapshot(
                        agent_id=self.agent_id,
                        state_type=StateType.AGENT_STATE,
                        data=self._state.copy(),
                        metadata=metadata,
                    )
                    await self.state_store.save_state(snapshot)
            except Exception as e:
                logger.error(
                    "Failed to save checkpoint",
                    error=str(e),
                    agent_id=self.agent_id
                )
            # Do not raise here; checkpoint failures should not abort execution

    async def cleanup(self) -> None:
        """Cleanup agent and persist final state."""
        try:
            if self.state_store:
                metadata = {
                    "execution_count": self._execution_count,
                    "metrics": self._metrics.copy(),
                    "config_version": self.config.version if self.config else None,
                }
                try:
                    final_type = getattr(StateType, 'FINAL', StateType.AGENT_STATE)
                    await self.state_store.save_state(
                        self.agent_id,
                        final_type,
                        self._state.copy(),
                        metadata,
                    )
                except TypeError:
                    snapshot = StateSnapshot(
                        agent_id=self.agent_id,
                        state_type=StateType.AGENT_STATE,
                        data=self._state.copy(),
                        metadata=metadata,
                    )
                    await self.state_store.save_state(snapshot)
        finally:
            # Clear runtime data
            self._state.clear()
            self._capabilities.clear()
            self._metrics.clear()
            logger.info(
                "Agent cleaned up",
                agent_id=self.agent_id,
                total_executions=self._execution_count,
            )

    def _clean_json_like_string(self, text: str) -> str:
        """Strip common code fences (```json ... ``` or ``` ... ```) and whitespace from LLM output."""
        t = text.strip()
        if t.startswith("```"):
            # Remove leading fence with optional language
            # e.g., ```json\n{...}\n``` or ```\n{...}\n```
            import re
            # Remove first line if it starts with triple backticks
            t = re.sub(r"^```[a-zA-Z]*\n", "", t)
            # Remove trailing triple backticks
            t = re.sub(r"\n```\s*$", "", t)
        # Also handle cases where fences appear inline
        if t.startswith('{') and t.endswith('}'):  # likely clean JSON already
            return t
        # If still wrapped, try to extract the first {...} block
        start = t.find('{')
        end = t.rfind('}')
        if start != -1 and end != -1 and end > start:
            return t[start:end+1]
        return t
    
    def _extract_metric_value(self, result: Any, metric_name: str) -> float:
        """Extract metric value from execution result"""
        try:
            # Handle different result types
            if isinstance(result, dict):
                if metric_name in result:
                    return float(result[metric_name])
                # Check nested metrics
                if "metrics" in result and metric_name in result["metrics"]:
                    return float(result["metrics"][metric_name])
            
            # Default metric values
            if metric_name == "completion_rate":
                return 1.0 if result else 0.0
            elif metric_name == "execution_time":
                return self._metrics.get("last_execution_time", 0.0)
            
            return 0.0
        except Exception:
            # If we can't extract metric, return 0
            return 0.0
    
    async def _execute_sequential(self, task: Any, context: Dict[str, Any]) -> Any:
        """Execute task sequentially"""
        # Simple sequential execution
        results = []
        
        if isinstance(task, list):
            for subtask in task:
                result = await self._execute_single_task(subtask, context)
                results.append(result)
                # Update context for next task
                context["previous_result"] = result
        else:
            results.append(await self._execute_single_task(task, context))
        
        return results[0] if len(results) == 1 else results
    
    async def _execute_parallel(self, task: Any, context: Dict[str, Any]) -> Any:
        """Execute task in parallel"""
        if isinstance(task, list):
            # Execute all subtasks in parallel
            tasks = [
                self._execute_single_task(subtask, context.copy())
                for subtask in task
            ]
            return await asyncio.gather(*tasks)
        else:
            return await self._execute_single_task(task, context)
    
    async def _execute_conditional(self, task: Any, context: Dict[str, Any]) -> Any:
        """Execute task conditionally"""
        # Simple conditional execution based on context
        if isinstance(task, dict) and "condition" in task:
            condition = task["condition"]
            if self._evaluate_condition(condition, context):
                return await self._execute_single_task(
                    task.get("then", {}),
                    context
                )
            else:
                return await self._execute_single_task(
                    task.get("else", {}),
                    context
                )
        else:
            return await self._execute_single_task(task, context)
    
    async def _execute_iterative(self, task: Any, context: Dict[str, Any]) -> Any:
        """Execute task iteratively"""
        results = []
        max_iterations = 10  # Safety limit
        
        if isinstance(task, dict) and "iterate" in task:
            iteration = 0
            while iteration < max_iterations:
                # Check continue condition before executing this iteration
                if "while" in task:
                    eval_context = {**context, "iteration": iteration}
                    if not self._evaluate_condition(task["while"], eval_context):
                        break
                
                result = await self._execute_single_task(
                    task["iterate"],
                    {**context, "iteration": iteration}
                )
                results.append(result)
                iteration += 1
        else:
            results.append(await self._execute_single_task(task, context))
        
        return results
    
    async def _execute_single_task(self, task: Any, context: Dict[str, Any]) -> Any:
        """Execute a single task"""
        # This is a simplified execution - in reality would use capabilities
        return {
            "task": task,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": self.agent_id
        }
    
    def _evaluate_condition(self, condition: Any, context: Dict[str, Any]) -> bool:
        """Evaluate a condition"""
        # Simple condition evaluation
        if isinstance(condition, bool):
            return condition
        elif isinstance(condition, str):
            # Evaluate with both direct names and 'context' mapping available
            local_vars = dict(context)
            local_vars['context'] = context
            return safe_eval_condition(condition, context=local_vars, default=False)
        elif isinstance(condition, dict):
            # Handle complex conditions
            if "field" in condition and "value" in condition:
                field_value = context.get(condition["field"])
                return field_value == condition["value"]

        return False
    
    async def _execute_with_tool_calling(
        self,
        prompt_template: str,
        context: Dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float,
        response_format: Optional[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_rounds: int = 5
    ) -> str:
        """Execute prompt with tool calling support.
        
        Similar to handle_arrow_chat_with_tools, this method:
        1. Calls LLM with tools
        2. Detects tool_calls in response
        3. Executes them using tool_executor
        4. Calls LLM again with tool results
        5. Repeats until no more tool calls or max rounds reached
        
        Args:
            prompt_template: Prompt template
            context: Execution context
            model: LLM model
            max_tokens: Max tokens
            temperature: Temperature
            response_format: Response format
            tools: Tool definitions
            max_rounds: Maximum tool calling rounds
            
        Returns:
            Final response content (string)
        """
        # Build workflow context from agent context
        # First check if workflow_context was passed directly (from workflow node execution)
        if "workflow_context" in context:
            workflow_context = context.get("workflow_context", {})
            # Merge any additional context fields that might be in the main context
            workflow_context = {
                **workflow_context,
                "spec_manager": context.get("spec_manager"),
                "workflow_manager": context.get("workflow_manager"),
                "available_plugins": context.get("available_plugins", workflow_context.get("available_plugins", [])),
                "available_agents": context.get("available_agents", workflow_context.get("available_agents", [])),
                "plugin_schemas": context.get("plugin_schemas", workflow_context.get("plugin_schemas", {})),
            }
        else:
            # Build workflow context from individual fields (for direct agent execution)
            workflow_context = {
                "workflow_runner": context.get("workflow_runner"),
                "execution_tree": context.get("execution_tree"),
                "get_execution_trace": context.get("get_execution_trace"),
                "spec_manager": context.get("spec_manager"),
                "workflow_manager": context.get("workflow_manager"),
                "available_plugins": context.get("available_plugins", []),
                "available_agents": context.get("available_agents", []),
                "plugin_schemas": context.get("plugin_schemas", {}),
            }
        
        # Fill template to get the prompt
        prompt = self.prompt_executor._fill_template(prompt_template, context)
        
        # Build conversation history
        messages = [{"role": "user", "content": prompt}]
        
        # Tool calling loop
        rounds = 0
        while rounds < max_rounds:
            # Call LLM with tools
            llm_response = await self.prompt_executor.llm_client.complete(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools if tools else None,
                response_format=response_format
            )
            
            # Extract message and tool_calls
            choice = llm_response.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls")
            
            # Add assistant message to history
            assistant_msg = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)
            
            # If no tool calls, return the final content
            if not tool_calls:
                logger.info(
                    "Tool calling completed",
                    agent_id=self.agent_id,
                    rounds=rounds,
                    final_content_length=len(content)
                )
                return content
            
            # Execute tool calls
            rounds += 1
            logger.info(
                "Executing tool calls",
                agent_id=self.agent_id,
                round=rounds,
                tool_count=len(tool_calls)
            )
            
            tool_results = await self.tool_executor.execute_tool_calls(
                tool_calls,
                workflow_context
            )
            
            # Add tool results to conversation
            messages.extend(tool_results)
        
        # Max rounds reached, return last content
        logger.warning(
            "Tool calling reached max rounds",
            agent_id=self.agent_id,
            rounds=rounds
        )
        return messages[-1].get("content", "") if messages else ""
