import pytest
from src.agents.base import Agent, AgentConfig
from src.agents.factory import AgentFactory


class MockAgent(Agent):
    async def execute(self, task):
        return {"mock": "result"}


class TestAgentFactory:
    
    @pytest.fixture(autouse=True)
    def clear_registry(self):
        # Clear registry before each test
        AgentFactory._registry = {}
        yield
        # Clear after test
        AgentFactory._registry = {}
    
    def test_register_agent_type(self):
        AgentFactory.register("mock", MockAgent)
        
        assert "mock" in AgentFactory._registry
        assert AgentFactory._registry["mock"] == MockAgent
    
    def test_register_duplicate_type_raises_error(self):
        AgentFactory.register("mock", MockAgent)
        
        with pytest.raises(ValueError, match="already registered"):
            AgentFactory.register("mock", MockAgent)
    
    def test_create_agent(self):
        AgentFactory.register("mock", MockAgent)
        
        config = AgentConfig(
            name="test_mock",
            agent_type="mock"
        )
        
        agent = AgentFactory.create(config)
        
        assert isinstance(agent, MockAgent)
        assert agent.config == config
        assert agent.id is not None
    
    def test_create_unknown_type_raises_error(self):
        config = AgentConfig(
            name="test_unknown",
            agent_type="unknown"
        )
        
        with pytest.raises(ValueError, match="Unknown agent type"):
            AgentFactory.create(config)
    
    def test_get_registered_types(self):
        AgentFactory.register("type1", MockAgent)
        AgentFactory.register("type2", MockAgent)
        
        types = AgentFactory.get_registered_types()
        
        assert set(types) == {"type1", "type2"}