# REVIEW:
# - Global registry has no reset or isolation; tests and runtime may leak registrations across contexts.
from typing import Type, Dict, List
from src.agents.base import Agent, AgentConfig
import structlog

logger = structlog.get_logger()


class AgentFactory:
    """Factory class for creating agents (SRP - only handles agent creation)"""
    
    _registry: Dict[str, Type[Agent]] = {}
    
    @classmethod
    def register(cls, agent_type: str, agent_class: Type[Agent]) -> None:
        """Register a new agent type"""
        if agent_type in cls._registry:
            raise ValueError(f"Agent type '{agent_type}' already registered")
        
        cls._registry[agent_type] = agent_class
        logger.info(f"Registered agent type: {agent_type}")
    
    @classmethod
    def create(cls, config: AgentConfig) -> Agent:
        """Create an agent instance"""
        agent_type = config.agent_type
        
        if agent_type not in cls._registry:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_class = cls._registry[agent_type]
        agent = agent_class(config)
        
        logger.info(
            f"Created agent",
            agent_id=agent.id,
            agent_type=agent_type,
            agent_name=config.name
        )
        
        return agent
    
    @classmethod
    def get_registered_types(cls) -> List[str]:
        """Get list of registered agent types"""
        return list(cls._registry.keys())
