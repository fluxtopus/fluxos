# REVIEW:
# - register_default_agents relies on global AgentFactory state; order of imports can affect available agents.
from src.agents.factory import AgentFactory
from src.agents.worker import WorkerAgent
from src.agents.parent import ParentAgent
from src.agents.mcp_agent import MCPAgent
from src.agents.llm_agent import (
    LLMWorkerAgent,
    LLMAnalyzerAgent,
    LLMValidatorAgent,
    LLMOrchestratorAgent
)
from src.agents.registry_agent import RegistryAgent
from src.agents.notifier import NotifierAgent
import structlog

logger = structlog.get_logger()


def register_default_agents():
    """Register default agent types"""
    
    def safe_register(name: str, cls):
        try:
            if name not in AgentFactory._registry:
                AgentFactory.register(name, cls)
        except Exception:
            # If already registered or any benign conflict, ignore to keep idempotent
            pass
    
    # Register worker agent
    safe_register("worker", WorkerAgent)
    
    # Register parent agent
    safe_register("parent", ParentAgent)
    
    # Register MCP agent
    safe_register("mcp", MCPAgent)
    
    # Register LLM-powered agents
    safe_register("llm_worker", LLMWorkerAgent)
    safe_register("llm_analyzer", LLMAnalyzerAgent)
    safe_register("llm_validator", LLMValidatorAgent)
    safe_register("llm_orchestrator", LLMOrchestratorAgent)
    
    # Register Registry Agent (for loading agents from the agent registry)
    safe_register("registry", RegistryAgent)
    
    # Register Notifier Agent (for notification delivery with BYOK)
    safe_register("notifier", NotifierAgent)

    logger.info(
        "Registered default agents",
        types=AgentFactory.get_registered_types()
    )
