import pytest
import asyncio
from src.agents.base import Agent, AgentConfig, AgentStatus
from src.agents.factory import AgentFactory
from src.agents.supervisor import AgentSupervisor


class TestSupervisorAgent(Agent):
    def __init__(self, config):
        super().__init__(config)
        self.task_data = None
    
    async def execute(self, task):
        self.task_data = task
        await asyncio.sleep(0.1)
        return {"status": "done"}


class TestAgentSupervisor:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        # Register test agent
        AgentFactory._registry = {}
        AgentFactory.register("test_supervisor", TestSupervisorAgent)
        yield
        AgentFactory._registry = {}
    
    @pytest.fixture
    def supervisor(self):
        return AgentSupervisor()
    
    @pytest.fixture
    def agent_config(self):
        return AgentConfig(
            name="test_agent",
            agent_type="test_supervisor"
        )
    
    @pytest.mark.asyncio
    async def test_spawn_agent(self, supervisor, agent_config):
        agent_id = await supervisor.spawn_agent(agent_config)
        
        assert agent_id is not None
        assert agent_id in supervisor._agents
        assert isinstance(supervisor._agents[agent_id], TestSupervisorAgent)
    
    @pytest.mark.asyncio
    async def test_start_agent(self, supervisor, agent_config):
        agent_id = await supervisor.spawn_agent(agent_config)
        task = {"type": "test"}
        
        # Start agent in background
        start_task = asyncio.create_task(
            supervisor.start_agent(agent_id, task)
        )
        
        # Wait a bit for agent to start
        await asyncio.sleep(0.05)
        
        agent = supervisor._agents[agent_id]
        assert agent.status == AgentStatus.RUNNING
        
        # Wait for completion
        await start_task
        
        assert agent.status == AgentStatus.COMPLETED
        assert agent.task_data == task
    
    @pytest.mark.asyncio
    async def test_stop_agent(self, supervisor, agent_config):
        agent_id = await supervisor.spawn_agent(agent_config)
        task = {"type": "long_running"}
        
        # Start agent
        start_task = asyncio.create_task(
            supervisor.start_agent(agent_id, task)
        )
        await asyncio.sleep(0.05)
        
        # Stop agent
        await supervisor.stop_agent(agent_id)
        
        # Clean up start task
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        
        agent = supervisor._agents[agent_id]
        assert agent.status == AgentStatus.STOPPED
    
    @pytest.mark.asyncio
    async def test_restart_agent(self, supervisor, agent_config):
        agent_id = await supervisor.spawn_agent(agent_config)
        task = {"type": "restart_test", "attempt": 1}
        
        # Start agent
        await supervisor.start_agent(agent_id, task)
        
        # Update task for restart
        task["attempt"] = 2
        
        # Restart agent
        await supervisor.restart_agent(agent_id, task)
        
        agent = supervisor._agents[agent_id]
        assert agent.task_data["attempt"] == 2
    
    def test_get_agent_status(self, supervisor):
        # Non-existent agent
        assert supervisor.get_agent_status("fake_id") is None
    
    @pytest.mark.asyncio
    async def test_get_all_agents(self, supervisor, agent_config):
        # Spawn multiple agents
        ids = []
        for i in range(3):
            config = AgentConfig(
                name=f"test_agent_{i}",
                agent_type="test_supervisor"
            )
            agent_id = await supervisor.spawn_agent(config)
            ids.append(agent_id)
        
        agents = supervisor.get_all_agents()
        
        assert len(agents) == 3
        for agent_state in agents:
            assert agent_state["id"] in ids
            assert agent_state["status"] == "idle"
    
    @pytest.mark.asyncio
    async def test_monitor_agents(self, supervisor, agent_config):
        # Start monitoring
        await supervisor.start_monitoring()
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        
        # Stop monitoring
        await supervisor.stop_monitoring()
        
        assert supervisor._monitor_task.done()