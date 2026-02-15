#!/usr/bin/env python3
"""Debug metrics collection."""

import asyncio
from src.agents.factory import AgentFactory
from src.agents.registry import register_default_agents
from src.agents.base import AgentConfig
from src.monitoring.metrics import agent_executions, MetricsCollector
from prometheus_client import generate_latest


async def test_metrics_debug():
    """Debug metrics collection."""
    print("Starting metrics debug...")
    
    # Register agents
    register_default_agents()
    
    # Test direct metric increment
    print("\n1. Testing direct metric increment...")
    agent_executions.labels(agent_type="test", agent_id="test-123", status="success").inc()
    
    # Check metrics
    metrics = generate_latest().decode()
    agent_lines = [l for l in metrics.split('\n') if 'tentackl_agent_executions_total' in l and 'test-123' in l]
    print(f"Found {len(agent_lines)} metric lines")
    for line in agent_lines:
        print(f"  {line}")
    
    # Test with decorator
    print("\n2. Testing with decorator...")
    
    @MetricsCollector.track_agent_execution("debug", "debug-456")
    async def test_function():
        await asyncio.sleep(0.1)
        return "done"
    
    result = await test_function()
    print(f"Function returned: {result}")
    
    # Check metrics again
    metrics = generate_latest().decode()
    agent_lines = [l for l in metrics.split('\n') if 'tentackl_agent_executions_total' in l and 'debug-456' in l]
    print(f"Found {len(agent_lines)} metric lines")
    for line in agent_lines:
        print(f"  {line}")
    
    # Test with agent
    print("\n3. Testing with actual agent...")
    config = AgentConfig(
        name="metrics-test-agent",
        agent_type="worker",
        timeout=10
    )
    
    agent = AgentFactory.create(config)
    print(f"Created agent: {agent.id}")
    
    # Check if start method has the decorator
    print(f"Agent.start method: {agent.start}")
    print(f"Agent class: {agent.__class__.__name__}")
    
    # Execute
    await agent.start({"action": "test"})
    
    # Check metrics
    metrics = generate_latest().decode()
    agent_lines = [l for l in metrics.split('\n') if 'tentackl_agent_executions_total' in l and agent.id in l]
    print(f"Found {len(agent_lines)} metric lines for agent {agent.id}")
    for line in agent_lines:
        print(f"  {line}")
    
    print("\nDebug completed!")


if __name__ == "__main__":
    asyncio.run(test_metrics_debug())