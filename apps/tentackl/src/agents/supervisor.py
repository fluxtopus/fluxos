# REVIEW:
# - Supervisor mixes production logic with test conveniences (create_agent, _global_agents).
# - Monitoring loop runs forever; no backoff or configurable interval.
from typing import Dict, List, Optional
from src.agents.base import Agent, AgentStatus, AgentConfig
from src.agents.factory import AgentFactory
import asyncio
import structlog

logger = structlog.get_logger()


class AgentSupervisor:
    """Manages agent lifecycle (SRP - only handles supervision)"""
    
    # Global registry so helper utilities (e.g., simple executors) can find agents
    _global_agents: Dict[str, Agent] = {}

    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._factory = AgentFactory
        self._monitor_task = None
    
    async def spawn_agent(self, config) -> str:
        """Spawn a new agent"""
        agent = self._factory.create(config)
        self._agents[agent.id] = agent
        AgentSupervisor._global_agents[agent.id] = agent
        
        logger.info(f"Spawned agent", agent_id=agent.id, agent_name=config.name)
        return agent.id
    
    async def start_agent(self, agent_id: str, task: Dict) -> None:
        """Start an agent with a task"""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self._agents[agent_id]
        await agent.start(task)
    
    async def stop_agent(self, agent_id: str) -> None:
        """Stop a running agent"""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self._agents[agent_id]
        await agent.stop()
    
    async def restart_agent(self, agent_id: str, task: Dict) -> None:
        """Restart an agent"""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found")
        agent = self._agents[agent_id]
        # If running, stop it; otherwise normalize to IDLE for clean restart
        if agent.status == AgentStatus.RUNNING:
            await self.stop_agent(agent_id)
        # Ensure we can start again
        agent.status = AgentStatus.IDLE
        await asyncio.sleep(0.05)
        await self.start_agent(agent_id, task)
    
    def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Get agent status"""
        agent = self._agents.get(agent_id)
        return agent.status if agent else None
    
    def get_all_agents(self) -> List[Dict]:
        """Get all agents and their states"""
        return [agent.get_state() for agent in self._agents.values()]
    
    async def monitor_agents(self) -> None:
        """Monitor agent health and restart if needed"""
        while True:
            try:
                for agent_id, agent in self._agents.items():
                    if agent.status == AgentStatus.FAILED:
                        logger.warning(f"Agent {agent_id} failed, considering restart")
                        # Implement restart logic based on config
                
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor error", error=str(e))
    
    async def start_monitoring(self) -> None:
        """Start agent monitoring"""
        if not self._monitor_task:
            self._monitor_task = asyncio.create_task(self.monitor_agents())
    
    async def stop_monitoring(self) -> None:
        """Stop agent monitoring"""
        if self._monitor_task:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)

    # Convenience APIs expected by integration tests
    async def create_agent(self, agent_type: str, name: str, config: Optional[Dict] = None) -> Agent:
        """Create an agent instance by type and name.

        For LLM agent types, construct specialized classes directly so tests can
        pass model/temperature via config. For other types, use AgentFactory.
        """
        config = config or {}
        try:
            if agent_type in {"llm_worker", "llm_analyzer", "llm_validator", "llm_orchestrator"}:
                from src.agents.llm_agent import (
                    LLMWorkerAgent, LLMAnalyzerAgent, LLMValidatorAgent, LLMOrchestratorAgent
                )
                llm_map = {
                    "llm_worker": LLMWorkerAgent,
                    "llm_analyzer": LLMAnalyzerAgent,
                    "llm_validator": LLMValidatorAgent,
                    "llm_orchestrator": LLMOrchestratorAgent,
                }
                cls = llm_map[agent_type]
                model = config.get("model") or "x-ai/grok-4.1-fast"
                temperature = config.get("temperature", 0.7)

                # Create AgentConfig for LLM agents
                agent_cfg = AgentConfig(
                    name=name,
                    agent_type=agent_type,
                    metadata={"model": model, "temperature": temperature}
                )
                agent = cls(
                    config=agent_cfg,
                    llm_client=config.get("llm_client"),  # Allow tests to pass custom client
                    enable_conversation_tracking=config.get("enable_conversation_tracking", True)
                )
            else:
                # Use factory for non-LLM agents
                agent_cfg = AgentConfig(name=name, agent_type=agent_type)
                agent = self._factory.create(agent_cfg)

            # Initialize agent before returning so it's ready to use
            if hasattr(agent, "initialize") and asyncio.iscoroutinefunction(agent.initialize):
                await agent.initialize()

            # Track and return
            self._agents[agent.id] = agent
            AgentSupervisor._global_agents[agent.id] = agent

            # No test-only adapters; expose the agent as-is
            return agent
        except Exception as e:
            logger.error("Failed to create agent", agent_type=agent_type, name=name, error=str(e))
            raise

    async def cleanup(self) -> None:
        """Shutdown all managed agents."""
        for agent in list(self._agents.values()):
            try:
                if hasattr(agent, "shutdown") and asyncio.iscoroutinefunction(agent.shutdown):
                    await agent.shutdown()
            except Exception:
                pass

    @classmethod
    def get_global_agent(cls, agent_id: str) -> Optional[Agent]:
        return cls._global_agents.get(agent_id)
