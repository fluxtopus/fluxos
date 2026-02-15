import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from src.agents.registry import register_default_agents
from src.agents.supervisor import AgentSupervisor
from src.agents.factory import AgentFactory
from src.llm.openrouter_client import OpenRouterClient
from src.interfaces.llm import LLMMessage, LLMResponse
from src.core.parallel_executor import ParallelExecutor
import structlog

logger = structlog.get_logger()


class TestLLMIntegration:
    """Integration tests for LLM functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        register_default_agents()
        yield
        # Cleanup
        AgentFactory._registry.clear()
    
    @pytest.mark.asyncio
    async def test_llm_agent_registration(self):
        """Test that LLM agents are properly registered"""
        registered_types = AgentFactory.get_registered_types()
        
        assert "llm_worker" in registered_types
        assert "llm_analyzer" in registered_types
        assert "llm_validator" in registered_types
        assert "llm_orchestrator" in registered_types
    
    @pytest.mark.asyncio
    async def test_create_llm_agent_with_supervisor(self):
        """Test creating LLM agent through supervisor"""
        supervisor = AgentSupervisor()
        
        # Mock the OpenRouter client
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.health_check = AsyncMock(return_value=True)
        
        with patch('src.agents.llm_agent.OpenRouterClient', return_value=mock_client):
            agent = await supervisor.create_agent(
                agent_type="llm_worker",
                name="test_llm_worker",
                config={
                    "model": "openai/gpt-3.5-turbo",
                    "temperature": 0.5
                }
            )
            
            assert agent is not None
            assert agent.name == "test_llm_worker"
            assert agent.model == "openai/gpt-3.5-turbo"
            
            await supervisor.cleanup()
    
    @pytest.mark.asyncio
    async def test_llm_workflow_execution(self):
        """Test executing a workflow with LLM agents"""
        supervisor = AgentSupervisor()
        executor = ParallelExecutor()
        
        # Mock LLM responses
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Analysis complete", "insights": ["insight1", "insight2"]}',
            model="test-model",
            usage={"total_tokens": 50}
        )
        
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.create_completion = AsyncMock(return_value=mock_response)
        
        with patch('src.agents.llm_agent.OpenRouterClient', return_value=mock_client):
            # Create multiple LLM agents
            analyzer1 = await supervisor.create_agent(
                agent_type="llm_analyzer",
                name="analyzer_1",
                config={"model": "openai/gpt-4o"}
            )
            
            analyzer2 = await supervisor.create_agent(
                agent_type="llm_analyzer",
                name="analyzer_2",
                config={"model": "anthropic/claude-3-haiku-20240307"}
            )
            
            # Execute tasks in parallel
            tasks = [
                {
                    "agent_id": analyzer1.agent_id,
                    "task": {
                        "description": "Analyze dataset A",
                        "data": {"dataset": "A"}
                    }
                },
                {
                    "agent_id": analyzer2.agent_id,
                    "task": {
                        "description": "Analyze dataset B",
                        "data": {"dataset": "B"}
                    }
                }
            ]
            
            results = await executor.execute_parallel(tasks)
            
            assert len(results) == 2
            assert all(r["status"] == "success" for r in results)
            # Insights are in the top-level result payload returned by the LLM
            assert all("insights" in r for r in results)
            
            await supervisor.cleanup()
    
    @pytest.mark.asyncio
    async def test_llm_error_handling(self):
        """Test error handling in LLM agents"""
        supervisor = AgentSupervisor()
        
        # Mock client that fails
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.create_completion = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )
        
        with patch('src.agents.llm_agent.OpenRouterClient', return_value=mock_client):
            agent = await supervisor.create_agent(
                agent_type="llm_worker",
                name="error_test_worker"
            )
            
            result = await agent.process_task({
                "description": "Test task",
                "data": {}
            })
            
            assert result["status"] == "error"
            assert "API rate limit exceeded" in result["error"]
            
            await supervisor.cleanup()
    
    @pytest.mark.asyncio
    async def test_llm_orchestrator_planning(self):
        """Test orchestrator agent planning capabilities"""
        supervisor = AgentSupervisor()
        
        # Mock orchestrator response
        plan_response = LLMResponse(
            content='''
            {
                "plan": {
                    "steps": [
                        {"id": "validate", "agent": "validator", "description": "Validate input data"},
                        {"id": "analyze", "agent": "analyzer", "description": "Analyze validated data"},
                        {"id": "report", "agent": "worker", "description": "Generate report"}
                    ],
                    "dependencies": {
                        "analyze": ["validate"],
                        "report": ["analyze"]
                    },
                    "agent_assignments": {
                        "validate": "llm_validator",
                        "analyze": "llm_analyzer",
                        "report": "llm_worker"
                    },
                    "expected_outcomes": {
                        "validate": "Data validation results",
                        "analyze": "Analysis insights",
                        "report": "Final report"
                    }
                },
                "metadata": {
                    "estimated_time": 180,
                    "complexity": "medium"
                }
            }
            ''',
            model="claude-3-5-sonnet-20241022"
        )
        
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.create_completion = AsyncMock(return_value=plan_response)
        
        with patch('src.agents.llm_agent.OpenRouterClient', return_value=mock_client):
            orchestrator = await supervisor.create_agent(
                agent_type="llm_orchestrator",
                name="master_planner"
            )
            
            plan = await orchestrator.create_execution_plan({
                "description": "Complex multi-stage analysis",
                "data": {"input": "test data"}
            })
            
            assert "plan" in plan
            assert len(plan["plan"]["steps"]) == 3
            assert "dependencies" in plan["plan"]
            assert plan["plan"]["dependencies"]["analyze"] == ["validate"]
            
            await supervisor.cleanup()
    
    @pytest.mark.asyncio
    async def test_mixed_agent_workflow(self):
        """Test workflow with both LLM and regular agents"""
        supervisor = AgentSupervisor()
        
        # Mock LLM client
        mock_llm_response = LLMResponse(
            content='{"status": "success", "validation": "passed", "score": 0.95}',
            model="test-model"
        )
        
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.create_completion = AsyncMock(return_value=mock_llm_response)
        
        with patch('src.agents.llm_agent.OpenRouterClient', return_value=mock_client):
            # Create regular worker
            worker = await supervisor.create_agent(
                agent_type="worker",
                name="data_processor"
            )
            
            # Create LLM validator
            validator = await supervisor.create_agent(
                agent_type="llm_validator",
                name="data_validator"
            )
            
            # Process with worker
            worker_result = await worker.execute({
                "type": "compute",
                "duration": 0.1
            })
            
            # Validate with LLM
            validation_result = await validator.process_task({
                "description": "Validate processed data",
                "data": worker_result
            })
            
            assert worker_result["status"] == "completed"
            assert validation_result["status"] == "success"
            assert validation_result["validation"] == "passed"
            assert validation_result["score"] == 0.95
            
            await supervisor.cleanup()
