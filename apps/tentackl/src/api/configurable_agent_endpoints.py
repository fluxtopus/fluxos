"""
API endpoints for ConfigurableAgent functionality
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import json
import uuid

from ..agents.configurable_agent import ConfigurableAgent
from ..config.agent_config_parser import AgentConfigParser
from ..capabilities.capability_registry import CapabilityRegistry
from ..execution.prompt_executor import PromptExecutor
from ..llm.openrouter_client import OpenRouterClient

# Import data stores
from ..budget.redis_budget_controller import RedisBudgetController
from ..state.redis_state_store import RedisStateStore
from ..context.redis_context_manager import RedisContextManager
from ..templates.redis_template_versioning import RedisTemplateVersioning

# Import interfaces
from ..interfaces.budget_controller import BudgetConfig, ResourceLimit, ResourceType
from ..interfaces.state_store import StateType
from ..interfaces.context_manager import ContextIsolationLevel
from ..interfaces.agent import AgentState

router = APIRouter(prefix="/api/v1/configurable-agents", tags=["configurable-agents"])

# In-memory store for active agents (in production, use Redis or database)
active_agents: Dict[str, ConfigurableAgent] = {}

# Shared components (initialize these at startup)
capability_registry = CapabilityRegistry()
config_parser = AgentConfigParser()
llm_client = OpenRouterClient()
prompt_executor = PromptExecutor(llm_client)

# Data stores
budget_controller = RedisBudgetController(
    redis_url="redis://redis:6379",
    db=7,
    key_prefix="api:budget"
)
state_store = RedisStateStore(
    redis_url="redis://redis:6379",
    db=8,
    key_prefix="api:state"
)
context_manager = RedisContextManager(
    redis_url="redis://redis:6379",
    db=9,
    key_prefix="api:context"
)
template_versioning = RedisTemplateVersioning(
    redis_url="redis://redis:6379",
    db=10,
    key_prefix="api:templates"
)


class CreateAgentRequest(BaseModel):
    """Request to create a new configurable agent"""
    agent_id: Optional[str] = Field(None, description="Agent ID (auto-generated if not provided)")
    config: Dict[str, Any] = Field(..., description="Agent configuration")
    enable_budget: bool = Field(False, description="Enable budget control")
    budget_limits: Optional[Dict[str, float]] = Field(None, description="Budget limits if enabled")
    enable_state: bool = Field(False, description="Enable state persistence")
    parent_agent_id: Optional[str] = Field(None, description="Parent agent ID for hierarchical setup")
    isolation_level: Optional[str] = Field("deep", description="Context isolation level")


class ExecuteTaskRequest(BaseModel):
    """Request to execute a task on an agent"""
    task: Dict[str, Any] = Field(..., description="Task data matching agent's state schema")


class AgentResponse(BaseModel):
    """Response with agent information"""
    agent_id: str
    config_name: str
    config_version: str
    state: str
    capabilities: List[str]
    execution_count: int
    created_at: datetime
    parent_id: Optional[str] = None


class ExecutionResponse(BaseModel):
    """Response from agent execution"""
    agent_id: str
    state: str
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    execution_time: float
    metrics: Dict[str, Any]


@router.post("/create", response_model=AgentResponse)
async def create_agent(request: CreateAgentRequest):
    """Create a new configurable agent"""
    try:
        # Generate agent ID if not provided
        agent_id = request.agent_id or f"agent-{uuid.uuid4()}"
        
        # Parse configuration
        config = await config_parser.parse(request.config)
        
        # Validate configuration
        validation = await config_parser.validate(config)
        if not validation["valid"]:
            raise HTTPException(400, detail={
                "message": "Invalid configuration",
                "errors": validation["errors"]
            })
        
        # Setup budget if enabled
        budget_ctrl = None
        if request.enable_budget:
            budget_ctrl = budget_controller
            
            # Create budget limits
            limits = []
            if request.budget_limits:
                for resource_type, limit in request.budget_limits.items():
                    limits.append(ResourceLimit(
                        resource_type=ResourceType(resource_type),
                        limit=limit,
                        hard_limit=True
                    ))
            else:
                # Default limits
                limits = [
                    ResourceLimit(ResourceType.LLM_CALLS, 100, hard_limit=True),
                    ResourceLimit(ResourceType.LLM_TOKENS, 10000, hard_limit=True),
                    ResourceLimit(ResourceType.LLM_COST, 1.0, hard_limit=True)
                ]
            
            budget_config = BudgetConfig(
                limits=limits,
                owner="api_user",
                created_at=datetime.utcnow(),
                metadata={"source": "api"}
            )
            
            if request.parent_agent_id:
                await budget_ctrl.create_child_budget(
                    request.parent_agent_id,
                    agent_id,
                    budget_config
                )
            else:
                await budget_ctrl.create_budget(agent_id, budget_config)
        
        # Setup state persistence if enabled
        state_str = state_store if request.enable_state else None
        
        # Setup context if hierarchical
        context_mgr = None
        if request.parent_agent_id:
            context_mgr = context_manager
            
            # Create or fork context
            isolation = ContextIsolationLevel(request.isolation_level)
            
            from ..interfaces.context_manager import ContextForkOptions
            fork_options = ContextForkOptions(
                isolation_level=isolation,
                inherit_variables=True,
                inherit_shared_resources=True
            )
            
            # Fork from parent context
            parent_contexts = await context_mgr.get_child_contexts(request.parent_agent_id)
            if parent_contexts:
                parent_context_id = parent_contexts[0].id
            else:
                # Create parent context if doesn't exist
                parent_context_id = await context_mgr.create_context(
                    agent_id=request.parent_agent_id,
                    isolation_level=ContextIsolationLevel.DEEP
                )
            
            await context_mgr.fork_context(
                parent_context_id,
                agent_id,
                fork_options
            )
        
        # Create agent
        agent = ConfigurableAgent(
            agent_id=agent_id,
            config=config,
            budget_controller=budget_ctrl,
            state_store=state_str,
            context_manager=context_mgr,
            capability_binder=capability_registry,
            prompt_executor=prompt_executor
        )
        
        # Store in active agents
        active_agents[agent_id] = agent
        
        # Wait for initialization
        await asyncio.sleep(0.1)
        
        return AgentResponse(
            agent_id=agent_id,
            config_name=config.name,
            config_version=config.version,
            state=AgentState.IDLE.value,
            capabilities=[cap.tool for cap in config.capabilities],
            execution_count=0,
            created_at=datetime.utcnow(),
            parent_id=request.parent_agent_id
        )
        
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.post("/{agent_id}/execute", response_model=ExecutionResponse)
async def execute_task(agent_id: str, request: ExecuteTaskRequest):
    """Execute a task on an agent"""
    if agent_id not in active_agents:
        raise HTTPException(404, detail="Agent not found")
    
    agent = active_agents[agent_id]
    
    try:
        # Execute task
        result = await agent.execute(request.task)
        
        return ExecutionResponse(
            agent_id=agent_id,
            state=result.state.value,
            result=result.result,
            error=result.error,
            execution_time=result.metadata.get("execution_time", 0),
            metrics=result.metadata.get("metrics", {})
        )
        
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    """Get agent information"""
    if agent_id not in active_agents:
        raise HTTPException(404, detail="Agent not found")
    
    agent = active_agents[agent_id]
    
    return AgentResponse(
        agent_id=agent_id,
        config_name=agent.config.name,
        config_version=agent.config.version,
        state=(await agent.get_state()).value,
        capabilities=list(agent.get_capabilities()),
        execution_count=agent._execution_count,
        created_at=datetime.utcnow()  # Should track actual creation time
    )


@router.get("/{agent_id}/state")
async def get_agent_state(agent_id: str):
    """Get agent's current state"""
    if agent_id not in active_agents:
        # Try to load from state store
        if state_store:
            latest_state = await state_store.get_latest_state(
                agent_id,
                StateType.AGENT_STATE
            )
            if latest_state:
                return {
                    "agent_id": agent_id,
                    "state": latest_state.data,
                    "metadata": latest_state.metadata,
                    "timestamp": latest_state.timestamp
                }
        
        raise HTTPException(404, detail="Agent not found")
    
    agent = active_agents[agent_id]
    return {
        "agent_id": agent_id,
        "state": agent._state,
        "execution_count": agent._execution_count,
        "metrics": agent._metrics
    }


@router.get("/{agent_id}/budget")
async def get_agent_budget(agent_id: str):
    """Get agent's budget usage"""
    try:
        usage = await budget_controller.get_usage(agent_id)
        
        return {
            "agent_id": agent_id,
            "usage": [
                {
                    "resource_type": u.resource_type.value,
                    "current": u.current,
                    "limit": u.limit,
                    "percentage": (u.current / u.limit * 100) if u.limit > 0 else 0
                }
                for u in usage
            ]
        }
    except Exception as e:
        raise HTTPException(404, detail="Budget not found for agent")


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent and clean up resources"""
    if agent_id not in active_agents:
        raise HTTPException(404, detail="Agent not found")
    
    agent = active_agents[agent_id]
    
    try:
        # Clean up agent
        await agent.cleanup()
        
        # Remove from active agents
        del active_agents[agent_id]
        
        return {"message": f"Agent {agent_id} deleted successfully"}
        
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.post("/upload-config")
async def upload_config(file: UploadFile = File(...)):
    """Upload and validate an agent configuration file"""
    if not file.filename.endswith(('.yaml', '.yml', '.json')):
        raise HTTPException(400, detail="File must be YAML or JSON")
    
    try:
        content = await file.read()
        
        if file.filename.endswith('.json'):
            config_dict = json.loads(content)
        else:
            config_dict = yaml.safe_load(content)
        
        # Parse and validate
        config = await config_parser.parse(config_dict)
        validation = await config_parser.validate(config)
        
        return {
            "filename": file.filename,
            "config": config_dict,
            "validation": validation
        }
        
    except Exception as e:
        raise HTTPException(400, detail=str(e))


@router.get("/templates/list")
async def list_templates():
    """List available agent templates"""
    try:
        # This would list templates from the template versioning system
        # For now, return example templates
        return {
            "templates": [
                {
                    "id": "data-analyzer-v1",
                    "name": "Data Analyzer",
                    "version": "1.0.0",
                    "description": "Analyzes data and provides insights"
                },
                {
                    "id": "code-reviewer-v1",
                    "name": "Code Reviewer",
                    "version": "1.0.0",
                    "description": "Reviews code for quality and security"
                },
                {
                    "id": "api-monitor-v1",
                    "name": "API Monitor",
                    "version": "1.0.0",
                    "description": "Monitors API endpoints"
                }
            ]
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@router.post("/templates/{template_id}/instantiate")
async def create_from_template(
    template_id: str,
    parameters: Optional[Dict[str, Any]] = None
):
    """Create an agent from a template"""
    try:
        # Get template
        latest = await template_versioning.get_latest_version(
            template_id,
            approved_only=True
        )
        
        if not latest:
            raise HTTPException(404, detail="Template not found")
        
        # Apply parameters
        config_dict = latest.content.copy()
        if parameters:
            # Replace template variables with parameters
            # This is a simplified version - real implementation would be more robust
            for key, value in parameters.items():
                for section in config_dict.values():
                    if isinstance(section, dict):
                        for k, v in section.items():
                            if isinstance(v, str) and f"{{{key}}}" in v:
                                section[k] = v.replace(f"{{{key}}}", str(value))
        
        # Create agent from config
        request = CreateAgentRequest(
            config=config_dict,
            enable_budget=True,
            enable_state=True
        )
        
        return await create_agent(request)
        
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# Add to your main FastAPI app
def register_configurable_agent_routes(app):
    """Register configurable agent routes with the main app"""
    app.include_router(router)