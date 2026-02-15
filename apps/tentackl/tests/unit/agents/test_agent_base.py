import pytest
import asyncio
from datetime import datetime
from src.agents.base import Agent, AgentConfig, AgentStatus, AgentMessage


class TestAgent(Agent):
    """Test implementation of Agent"""
    
    def __init__(self, config: AgentConfig, should_fail: bool = False):
        super().__init__(config)
        self.should_fail = should_fail
        self.execute_called = False
        self.task_received = None
    
    async def execute(self, task):
        self.execute_called = True
        self.task_received = task
        
        if self.should_fail:
            raise Exception("Test failure")
        
        await asyncio.sleep(0.1)
        return {"result": "success"}


class TestAgentBase:
    
    @pytest.fixture
    def agent_config(self):
        return AgentConfig(
            name="test_agent",
            agent_type="test",
            timeout=60,
            max_retries=3,
            capabilities=["test"],
            metadata={"test": True}
        )
    
    def test_agent_initialization(self, agent_config):
        agent = TestAgent(agent_config)
        
        assert agent.config == agent_config
        assert agent.status == AgentStatus.IDLE
        assert isinstance(agent.created_at, datetime)
        assert agent.id is not None
        assert agent._task is None
    
    @pytest.mark.asyncio
    async def test_agent_start_success(self, agent_config):
        agent = TestAgent(agent_config)
        task = {"type": "test_task"}
        
        await agent.start(task)
        
        assert agent.execute_called
        assert agent.task_received == task
        assert agent.status == AgentStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_agent_start_failure(self, agent_config):
        agent = TestAgent(agent_config, should_fail=True)
        task = {"type": "test_task"}
        
        with pytest.raises(Exception, match="Test failure"):
            await agent.start(task)
        
        assert agent.status == AgentStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_agent_stop(self, agent_config):
        agent = TestAgent(agent_config)
        task = {"type": "long_task"}
        
        # Start agent in background
        start_task = asyncio.create_task(agent.start(task))
        await asyncio.sleep(0.05)  # Let it start
        
        # Stop the agent
        await agent.stop()
        
        # Wait for start task to complete
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        
        assert agent.status == AgentStatus.STOPPED
    
    def test_agent_get_state(self, agent_config):
        agent = TestAgent(agent_config)
        state = agent.get_state()
        
        assert state["id"] == agent.id
        assert state["name"] == "test_agent"
        assert state["type"] == "test"
        assert state["status"] == "idle"
        assert "created_at" in state


class TestAgentMessage:
    
    def test_agent_message_creation(self):
        message = AgentMessage(
            sender_id="agent1",
            recipient_id="agent2",
            content={"data": "test"},
            message_type="test"
        )
        
        assert message.sender_id == "agent1"
        assert message.recipient_id == "agent2"
        assert message.content == {"data": "test"}
        assert message.message_type == "test"
        assert isinstance(message.timestamp, datetime)
        assert message.id is not None
    
    def test_agent_message_defaults(self):
        message = AgentMessage(
            sender_id="agent1",
            content={}
        )
        
        assert message.recipient_id is None
        assert message.message_type == "default"